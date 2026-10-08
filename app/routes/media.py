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
from app.auth import Principal, require_auth
from app.db import fetchrow
from app.errors import ApiError
from app.media import parse_byte_range

router = APIRouter(dependencies=[Depends(require_auth)])


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
    asset_id: uuid.UUID, request: Request, principal: Principal = Depends(require_auth)
) -> Response:
    asset = await fetchrow(
        """SELECT a.object_key, a.mime_type FROM assets a
           WHERE a.id=$1 AND a.user_id=$2 AND a.status IN ('uploaded', 'attached')
           AND EXISTS (SELECT 1 FROM memory_assets ma JOIN memories m ON m.id=ma.memory_id
                       WHERE ma.asset_id=a.id AND ma.user_id=a.user_id
                       AND m.user_id=a.user_id AND m.deleted_at IS NULL)""",
        asset_id,
        uuid.UUID(principal.id),
    )
    if asset is None:
        raise ApiError(404, "media_not_found", "This file is no longer available.")
    return await _deliver(request, StoredMedia.model_validate(asset))


@router.get("/memories/{memory_id}/preview")
async def memory_preview(
    memory_id: uuid.UUID, request: Request, principal: Principal = Depends(require_auth)
) -> Response:
    asset = await fetchrow(
        """SELECT a.object_key, a.mime_type FROM memories m
           JOIN memory_assets ma ON ma.memory_id=m.id AND ma.user_id=m.user_id
           JOIN assets a ON a.id=ma.asset_id AND a.user_id=m.user_id
           WHERE m.id=$1 AND m.user_id=$2 AND m.deleted_at IS NULL
             AND a.status IN ('uploaded', 'attached') ORDER BY ma.position LIMIT 1""",
        memory_id,
        uuid.UUID(principal.id),
    )
    if asset is None:
        raise ApiError(404, "media_not_found", "This preview is no longer available.")
    return await _deliver(request, StoredMedia.model_validate(asset))
