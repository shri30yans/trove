"""Authenticated media bytes. Provider URLs and credentials never cross this boundary."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import anyio
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app import storage
from app.auth import AUTH_SUBJECT_CTE, VerifiedSubject, require_subject, resolve_auth_state
from app.db import fetchrow
from app.errors import ApiError
from app.media import parse_byte_range

router = APIRouter()


class StoredMedia(BaseModel):
    object_key: str = Field(min_length=1)
    mime_type: str = Field(pattern=r"^[\w.+-]+/[\w.+-]+$")


async def _deliver(request: Request, asset: StoredMedia) -> Response:
    try:
        size = await storage.head_object_size(asset.object_key)
        selection = None
        if request.headers.get("range"):
            try:
                selection = parse_byte_range(request.headers["range"], size)
            except ValueError:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        body, length = await storage.open_object_stream(
            asset.object_key, f"bytes={selection.start}-{selection.end}" if selection else None
        )
    except ClientError as error:
        if error.response["Error"]["Code"] in {"NoSuchKey", "NotFound", "404"}:
            raise ApiError(404, "media_not_found", "This file is no longer available.") from error
        raise ApiError(503, "media_unavailable", "This file could not be loaded. Try again.") from error

    except (BotoCoreError, OSError) as error:
        raise ApiError(503, "media_unavailable", "This file could not be loaded. Try again.") from error

    async def close() -> None:
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(body.close)

    if length != (selection.length if selection else size):
        await close()
        raise ApiError(502, "invalid_media_response", "The file service returned an invalid response.")

    async def chunks() -> AsyncIterator[bytes]:
        try:
            while chunk := await anyio.to_thread.run_sync(body.read, 256 * 1024):
                yield chunk
        finally:
            await close()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if selection:
        headers["Content-Range"] = f"bytes {selection.start}-{selection.end}/{size}"
    return StreamingResponse(
        chunks(),
        status_code=206 if selection else 200,
        media_type=asset.mime_type,
        headers=headers,
        background=BackgroundTask(close),
    )


@router.get("/assets/{asset_id}/content")
async def asset_content(
    asset_id: uuid.UUID, request: Request, subject: VerifiedSubject = Depends(require_subject)
) -> Response:
    asset = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT a.deleted, a.deletion_pending, a.user_id, found.object_key, found.mime_type
            FROM auth a
            LEFT JOIN LATERAL (
              SELECT a2.object_key, a2.mime_type FROM assets a2
              WHERE a2.id=$4 AND a2.user_id=a.user_id AND a2.status IN ('uploaded', 'attached')
              AND EXISTS (SELECT 1 FROM memory_assets ma JOIN memories m ON m.id=ma.memory_id
                          WHERE ma.asset_id=a2.id AND ma.user_id=a2.user_id
                          AND m.user_id=a2.user_id AND m.deleted_at IS NULL)
            ) found ON NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL""",
        subject.subject,
        subject.email,
        subject.display_name,
        asset_id,
    )
    if asset is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(asset)
    if asset["object_key"] is None:
        raise ApiError(404, "media_not_found", "This file is no longer available.")
    return await _deliver(request, StoredMedia.model_validate(asset))


@router.get("/memories/{memory_id}/preview")
async def memory_preview(
    memory_id: uuid.UUID, request: Request, subject: VerifiedSubject = Depends(require_subject)
) -> Response:
    asset = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT a.deleted, a.deletion_pending, a.user_id, found.object_key, found.mime_type
            FROM auth a
            LEFT JOIN LATERAL (
              SELECT a2.object_key, a2.mime_type FROM memories m
              JOIN memory_assets ma ON ma.memory_id=m.id AND ma.user_id=m.user_id
              JOIN assets a2 ON a2.id=ma.asset_id AND a2.user_id=m.user_id
              WHERE m.id=$4 AND m.user_id=a.user_id AND m.deleted_at IS NULL
                AND a2.status IN ('uploaded', 'attached') ORDER BY ma.position LIMIT 1
            ) found ON NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL""",
        subject.subject,
        subject.email,
        subject.display_name,
        memory_id,
    )
    if asset is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(asset)
    if asset["object_key"] is None:
        raise ApiError(404, "media_not_found", "This preview is no longer available.")
    return await _deliver(request, StoredMedia.model_validate(asset))
