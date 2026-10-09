"""Upload allocation, transfer and verified completion."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app import storage
from app.auth import Principal, as_uuid, require_auth
from app.config import get_config
from app.db import execute, fetchrow, transaction
from app.domain.enums import AssetStatus
from app.domain.plans import StoragePlan, get_storage_plan
from app.errors import ApiError, ApiJSONResponse, respond
from app.schemas import CreateUploadRequest, parse_body
from app.serialize import WireModel
from app.upload_admission import UploadAdmissionFull, upload_admission
from app.upload_transfer import (
    TransferRecord,
    UploadRecord,
    fail_reservation_quietly,
    invalidate_reservation,
    receive_and_store,
    storage_operation,
)

logger = logging.getLogger("trove.uploads")
router = APIRouter(dependencies=[Depends(require_auth)])
_MIME = re.compile(r"^[\w.+-]+/[\w.+-]+$")


class UploadAllocation(WireModel):
    """Where the client puts the bytes, and only that. The bucket stays on the server."""

    assetId: uuid.UUID
    uploadPath: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]


class UploadReceipt(WireModel):
    assetId: uuid.UUID
    byteSize: int = Field(strict=True, gt=0)


class UploadCompletion(UploadReceipt):
    status: Literal[AssetStatus.UPLOADED, AssetStatus.ATTACHED]


def _plan_or_error(plan_id: str) -> StoragePlan:
    """The persisted plan, or the API's answer when stored plan data names one this build cannot serve."""
    try:
        return get_storage_plan(plan_id)
    except ValueError as error:
        raise ApiError(500, "invalid_storage_plan", "The account plan is not supported.") from error


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
        plan = _plan_or_error(account["storage_plan"])
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
        ),
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
    record = TransferRecord.from_row(asset)
    if record.status == AssetStatus.UPLOADED or record.status == AssetStatus.ATTACHED:
        raise ApiError(409, "upload_already_complete", "This upload is already complete.")
    if record.status == AssetStatus.FAILED:
        raise ApiError(409, "upload_invalidated", "This upload allocation expired. Start the save again.")
    expected = record.byte_size
    maximum = get_config().MAX_UPLOAD_BYTES
    if expected > maximum:
        raise ApiError(413, "upload_too_large", "This file exceeds the upload limit.")
    plan = _plan_or_error(str(asset["storage_plan"]))

    try:
        wait_ms = await upload_admission.acquire(paid_plan=plan.id == "paid")
    except UploadAdmissionFull as error:
        logger.warning("upload_admission_rejected asset_id=%s plan=%s", asset_id, plan.id)
        await invalidate_reservation(asset_id, user_id)
        raise ApiError(
            429, "upload_queue_full", "Sync is busy. This save remains on your device and will retry."
        ) from error
    except asyncio.CancelledError:
        await fail_reservation_quietly(asset_id, user_id, "admission")
        raise

    try:
        if wait_ms >= 10:
            logger.info("upload_admitted asset_id=%s plan=%s queue_wait_ms=%s", asset_id, plan.id, round(wait_ms))
        logger.info("upload_receive_started asset_id=%s expected_bytes=%s", asset_id, expected)
        transfer_started = time.monotonic()
        received = await receive_and_store(request, asset_id, user_id, record, expected, maximum)
        transfer_ms = round((time.monotonic() - transfer_started) * 1000)
    finally:
        await upload_admission.release()
    logger.info("upload_storage_succeeded asset_id=%s bytes=%s elapsed_ms=%s", asset_id, received, transfer_ms)
    return respond(UploadReceipt(assetId=as_uuid(asset_id), byteSize=received))


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
    record = UploadRecord.from_row(asset)
    if record.status == AssetStatus.UPLOADED or record.status == AssetStatus.ATTACHED:
        return respond(UploadCompletion(assetId=as_uuid(asset_id), status=record.status, byteSize=record.byte_size))
    if record.status == AssetStatus.FAILED:
        raise ApiError(409, "upload_invalidated", "This upload allocation expired. Start the save again.")
    with storage_operation(asset_id, "completion"):
        actual_size = await storage.head_object_size(record.object_key)
    if not actual_size or actual_size != record.byte_size or actual_size > get_config().MAX_UPLOAD_BYTES:
        raise ApiError(422, "upload_size_mismatch", "The uploaded file size did not match the declared size.")
    await execute(
        "UPDATE assets SET status='uploaded', uploaded_at=now() WHERE id=$1 AND user_id=$2",
        as_uuid(asset_id),
        user_id,
    )
    logger.info("upload_completed asset_id=%s bytes=%s", asset_id, actual_size)
    return respond(UploadCompletion(assetId=as_uuid(asset_id), status=AssetStatus.UPLOADED, byteSize=actual_size))
