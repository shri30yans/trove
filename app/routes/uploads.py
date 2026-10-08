"""Authenticated upload allocation, transfer and verified completion."""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import anyio
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, ValidationError

from app import storage
from app.auth import Principal, as_uuid, require_auth
from app.config import get_config
from app.db import execute, fetchrow, transaction
from app.domain.enums import AssetStatus
from app.domain.plans import get_storage_plan
from app.errors import ApiError, ApiJSONResponse, respond
from app.schemas import CreateUploadRequest, parse_body
from app.upload_admission import UploadAdmissionFull, upload_admission

logger = logging.getLogger("trove.uploads")
router = APIRouter(dependencies=[Depends(require_auth)])
_MIME = re.compile(r"^[\w.+-]+/[\w.+-]+$")


class UploadRecord(BaseModel):
    object_key: str = Field(min_length=1)
    byte_size: int = Field(strict=True, gt=0)
    status: AssetStatus


class TransferRecord(UploadRecord):
    mime_type: str = Field(pattern=r"^[\w.+-]+/[\w.+-]+$")


class UploadAllocation(BaseModel):
    assetId: uuid.UUID
    uploadPath: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]


class UploadReceipt(BaseModel):
    assetId: uuid.UUID
    byteSize: int = Field(strict=True, gt=0)


class UploadCompletion(UploadReceipt):
    status: Literal[AssetStatus.UPLOADED, AssetStatus.ATTACHED]


async def _receive_and_store_upload(
    request: Request,
    asset_id: str,
    user_id: uuid.UUID,
    record: TransferRecord,
    expected: int,
    maximum: int,
) -> int:
    received = 0
    with tempfile.TemporaryDirectory(prefix="trove-upload-") as directory:
        path = str(Path(directory) / "content")
        try:
            async with await anyio.open_file(path, "wb") as output:
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > min(expected, maximum):
                        raise ApiError(413, "upload_too_large", "The file exceeds its declared size.")
                    await output.write(chunk)
        except BaseException:
            # No object write has started. Storage errors below stay reserved because the provider
            # may have accepted a write before returning an error.
            try:
                await execute(
                    "UPDATE assets SET status='failed' WHERE id=$1 AND user_id=$2 AND status='pending_upload'",
                    as_uuid(asset_id),
                    user_id,
                )
            except Exception as error:  # noqa: BLE001 - preserve the transfer error and record cleanup failure
                logger.warning(
                    "upload_reservation_cleanup_failed asset_id=%s stage=receive error_type=%s",
                    asset_id,
                    type(error).__name__,
                )
            raise
        if received != expected:
            await execute(
                "UPDATE assets SET status='failed' WHERE id=$1 AND user_id=$2 AND status='pending_upload'",
                as_uuid(asset_id),
                user_id,
            )
            raise ApiError(422, "upload_size_mismatch", "The uploaded file size did not match the declared size.")
        with storage_operation(asset_id, "transfer"):
            await storage.upload_file(path, record.object_key, record.mime_type)
    return received


@contextmanager
def storage_operation(asset_id: str, stage: str) -> Iterator[None]:
    """Translate provider failures at the API boundary without logging private provider details."""
    try:
        yield
    except ClientError as error:
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = error.response.get("Error", {}).get("Code")
        logger.warning("upload_storage_rejected asset_id=%s stage=%s storage_status=%s", asset_id, stage, status)
        if status in (401, 403) or code in {"InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied"}:
            raise ApiError(
                503,
                "storage_access_denied",
                "The server cannot access file storage. Its storage credentials and bucket need checking. Your save is kept on this device.",
            ) from error
        raise ApiError(
            502, "storage_unavailable", "File storage is unavailable. Your save is kept on this device."
        ) from error
    except (BotoCoreError, OSError) as error:
        logger.warning(
            "upload_storage_failed asset_id=%s stage=%s error_type=%s", asset_id, stage, type(error).__name__
        )
        raise ApiError(
            502, "storage_unavailable", "File storage is unavailable. Your save is kept on this device."
        ) from error


@router.post("/uploads")
async def create_upload(request: Request, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    payload = await parse_body(CreateUploadRequest, request, "invalid_upload", "Invalid upload.")
    config = get_config()
    if payload.byteSize > config.MAX_UPLOAD_BYTES:
        raise ApiError(413, "upload_too_large", "This file is larger than the configured upload limit.")
    if not _MIME.match(payload.mimeType):
        raise ApiError(400, "invalid_mime_type", "A valid MIME type is required.")
    user_id = uuid.UUID(principal.id)
    object_key = storage.new_object_key(str(user_id), payload.filename)
    async with transaction() as connection:
        account = await connection.fetchrow("SELECT storage_plan FROM app_users WHERE id=$1 FOR UPDATE", user_id)
        if account is None:
            raise ApiError(500, "account_not_found", "The account plan could not be loaded.")
        try:
            plan = get_storage_plan(account["storage_plan"])
        except ValueError as error:
            raise ApiError(500, "invalid_storage_plan", "The account plan is not supported.") from error
        used_bytes = await connection.fetchval(
            """SELECT COALESCE(SUM(byte_size),0)::bigint FROM assets
               WHERE user_id=$1 AND status IN ('pending_upload','uploaded','attached')""",
            user_id,
        )
        if int(used_bytes) + payload.byteSize > plan.limit_bytes:
            raise ApiError(
                413,
                "storage_quota_exceeded",
                f"This upload would exceed your {plan.name} plan storage limit. Your saves remain on this device.",
            )
        created = await connection.fetchrow(
            """INSERT INTO assets(user_id, object_key, original_filename, mime_type, byte_size, checksum_sha256)
               VALUES($1,$2,$3,$4,$5,$6) RETURNING id""",
            user_id,
            object_key,
            payload.filename,
            payload.mimeType,
            payload.byteSize,
            payload.checksumSha256,
        )
    if created is None:
        raise ApiError(500, "internal_error", "The request could not be completed.")
    asset_id = created["id"]
    return respond(
        UploadAllocation(
            assetId=asset_id, uploadPath=f"/v1/uploads/{asset_id}/content", headers={"Content-Type": payload.mimeType}
        ).model_dump(mode="json"),
        201,
    )


@router.put("/uploads/{asset_id}/content")
async def upload_content(
    asset_id: str, request: Request, principal: Principal = Depends(require_auth)
) -> ApiJSONResponse:
    """Authenticated, bounded streaming upload; storage credentials stay on the API."""
    user_id = uuid.UUID(principal.id)
    asset = await fetchrow(
        """SELECT a.object_key, a.byte_size, a.mime_type, a.status, u.storage_plan
           FROM assets a JOIN app_users u ON u.id=a.user_id
           WHERE a.id=$1 AND a.user_id=$2""",
        as_uuid(asset_id),
        user_id,
    )
    if asset is None:
        raise ApiError(404, "upload_not_found", "Upload not found.")
    try:
        record = TransferRecord.model_validate(asset)
    except ValidationError as error:
        raise ApiError(500, "invalid_upload_record", "The upload record is invalid.") from error
    if record.status in (AssetStatus.UPLOADED, AssetStatus.ATTACHED):
        raise ApiError(409, "upload_already_complete", "This upload is already complete.")
    if record.status == AssetStatus.FAILED:
        raise ApiError(409, "upload_invalidated", "This upload allocation expired. Start the save again.")
    expected = record.byte_size
    maximum = get_config().MAX_UPLOAD_BYTES
    if expected > maximum:
        raise ApiError(413, "upload_too_large", "This file exceeds the upload limit.")
    try:
        plan = get_storage_plan(str(asset["storage_plan"]))
    except ValueError as error:
        raise ApiError(500, "invalid_storage_plan", "The account plan is not supported.") from error

    try:
        wait_ms = await upload_admission.acquire(paid_plan=plan.id == "paid")
    except UploadAdmissionFull as error:
        logger.warning("upload_admission_rejected asset_id=%s plan=%s", asset_id, plan.id)
        await execute(
            "UPDATE assets SET status='failed' WHERE id=$1 AND user_id=$2 AND status='pending_upload'",
            as_uuid(asset_id),
            user_id,
        )
        raise ApiError(
            429, "upload_queue_full", "Sync is busy. This save remains on your device and will retry."
        ) from error
    except asyncio.CancelledError:
        try:
            await execute(
                "UPDATE assets SET status='failed' WHERE id=$1 AND user_id=$2 AND status='pending_upload'",
                as_uuid(asset_id),
                user_id,
            )
        except Exception as error:  # noqa: BLE001 - preserve cancellation while recording cleanup failure
            logger.warning(
                "upload_reservation_cleanup_failed asset_id=%s stage=admission error_type=%s",
                asset_id,
                type(error).__name__,
            )
        raise

    try:
        if wait_ms >= 10:
            logger.info("upload_admitted asset_id=%s plan=%s queue_wait_ms=%s", asset_id, plan.id, round(wait_ms))
        logger.info("upload_receive_started asset_id=%s expected_bytes=%s", asset_id, expected)
        transfer_started = time.monotonic()
        received = await _receive_and_store_upload(request, asset_id, user_id, record, expected, maximum)
        transfer_ms = round((time.monotonic() - transfer_started) * 1000)
    finally:
        await upload_admission.release()
    logger.info("upload_storage_succeeded asset_id=%s bytes=%s elapsed_ms=%s", asset_id, received, transfer_ms)
    return respond(UploadReceipt(assetId=as_uuid(asset_id), byteSize=received).model_dump(mode="json"))


@router.post("/uploads/{asset_id}/complete")
async def complete_upload(asset_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    user_id = uuid.UUID(principal.id)
    asset = await fetchrow(
        "SELECT object_key, byte_size, status FROM assets WHERE id=$1 AND user_id=$2",
        as_uuid(asset_id),
        user_id,
    )
    if asset is None:
        raise ApiError(404, "upload_not_found", "Upload not found.")
    try:
        record = UploadRecord.model_validate(asset)
    except ValidationError as error:
        raise ApiError(500, "invalid_upload_record", "The upload record is invalid.") from error
    expected_size = record.byte_size
    status = record.status
    if status == AssetStatus.UPLOADED or status == AssetStatus.ATTACHED:
        return respond(
            UploadCompletion(assetId=as_uuid(asset_id), status=status, byteSize=expected_size).model_dump(mode="json")
        )
    if status == AssetStatus.FAILED:
        raise ApiError(409, "upload_invalidated", "This upload allocation expired. Start the save again.")
    with storage_operation(asset_id, "completion"):
        actual_size = await storage.head_object_size(record.object_key)
    if not actual_size or actual_size != expected_size or actual_size > get_config().MAX_UPLOAD_BYTES:
        raise ApiError(422, "upload_size_mismatch", "The uploaded file size did not match the declared size.")
    await execute(
        "UPDATE assets SET status='uploaded', uploaded_at=now() WHERE id=$1 AND user_id=$2",
        as_uuid(asset_id),
        user_id,
    )
    logger.info("upload_completed asset_id=%s bytes=%s", asset_id, actual_size)
    return respond(
        UploadCompletion(assetId=as_uuid(asset_id), status=AssetStatus.UPLOADED, byteSize=actual_size).model_dump(
            mode="json"
        )
    )
