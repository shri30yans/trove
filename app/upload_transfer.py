"""Moving one upload's bytes from the request into Storage.

This is the transport boundary of an upload: the streamed receive, the size rules that stop it, the
provider write, and the translation of provider failures into the API's error contract. It owns no
status decision beyond the one its own failure forces — a reservation this module could not finish is
marked failed so the space it held is returned to the plan quota.

The route keeps what the caller sees: the admission gate, the 404/409 answers about the allocation's
state, and the receipt. Transactions never cross in here; completion re-verifies against the provider
instead of trusting a write this module reported.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Self

import anyio
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request

from app import storage
from app.auth import as_uuid
from app.db import execute
from app.domain.enums import AssetStatus
from app.errors import ApiError
from app.serialize import Row

logger = logging.getLogger("trove.uploads")


class UploadRecord(BaseModel):
    """The persisted allocation, as the completion check needs to see it.

    `byte_size` is read as the exact number it was declared with: asyncpg hands back an int, and a row
    that says otherwise is corrupt storage, not a request to reinterpret.
    """

    object_key: str = Field(min_length=1)
    byte_size: int = Field(strict=True, gt=0)
    status: AssetStatus

    @classmethod
    def from_row(cls, row: Row) -> Self:
        """Validate the stored row, or fail as a broken record rather than a broken request."""
        try:
            return cls.model_validate(row)
        except ValidationError as error:
            raise ApiError(500, "invalid_upload_record", "The upload record is invalid.") from error


class TransferRecord(UploadRecord):
    """The same allocation while bytes are still moving, which also needs its MIME type."""

    mime_type: str = Field(pattern=r"^[\w.+-]+/[\w.+-]+$")


async def invalidate_reservation(asset_id: str, user_id: uuid.UUID) -> None:
    """Return a reservation's bytes to the plan quota after its transfer did not complete.

    Only a row still waiting for its upload is touched, so this is safe beside a completion that
    already ran.
    """
    await execute(
        "UPDATE assets SET status='failed' WHERE id=$1 AND user_id=$2 AND status='pending_upload'",
        as_uuid(asset_id),
        user_id,
    )


async def fail_reservation_quietly(asset_id: str, user_id: uuid.UUID, stage: str) -> None:
    """Release a reservation without letting a cleanup failure replace the transfer's own error.

    The client's answer stays the transfer failure, which is the one it can act on. A cleanup that
    itself failed is logged with the stage it happened in; the row is left pending, and a later
    attempt on the same asset either completes it or fails it again.
    """
    try:
        await invalidate_reservation(asset_id, user_id)
    except Exception as error:  # noqa: BLE001 - preserve the transfer error and record cleanup failure
        logger.warning(
            "upload_reservation_cleanup_failed asset_id=%s stage=%s error_type=%s",
            asset_id,
            stage,
            type(error).__name__,
        )


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


async def receive_and_store(
    request: Request,
    asset_id: str,
    user_id: uuid.UUID,
    record: TransferRecord,
    expected: int,
    maximum: int,
) -> int:
    """Stream the request body to a temporary file, then write it to Storage once it is verified.

    Nothing reaches the provider until the byte count matches what the allocation declared, so a
    truncated or padded body cannot become a stored object.
    """
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
            await fail_reservation_quietly(asset_id, user_id, "receive")
            raise
        if received != expected:
            await invalidate_reservation(asset_id, user_id)
            raise ApiError(422, "upload_size_mismatch", "The uploaded file size did not match the declared size.")
        with storage_operation(asset_id, "transfer"):
            await storage.upload_file(path, record.object_key, record.mime_type)
    return received
