"""Memory CRUD and the retry/restore endpoints."""

from __future__ import annotations

import base64
import datetime as dt
import logging
import re
import time
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from app.auth import Principal, as_uuid, require_auth
from app.db import fetch, fetchrow, transaction
from app.domain.enums import MemoryStatus
from app.domain.retrieval import LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT, LIST_MIN_LIMIT, parse_limit
from app.errors import ApiError, ApiJSONResponse, iso_milliseconds, respond
from app.queries import PREVIEW_KEY_SUBQUERY
from app.queue import enqueue_memory_processing
from app.schemas import (
    CreateMemoryRequest,
    MoveMemoryRequest,
    UpdateMemoryRequest,
    parse_body,
    parse_kind_param,
    source_domain,
)
from app.serialize import memory_card
from app.times import parse_timestamp

router = APIRouter(dependencies=[Depends(require_auth)])
logger = logging.getLogger("trove.api")

_MEMORY_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _uuids(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(value) for value in values]


async def _validate_owned_ids(user_id: uuid.UUID, ids: list[str], table: str) -> bool:
    values = _unique(ids)
    if not values:
        return True
    sql = (
        "SELECT id FROM spaces WHERE user_id = $1 AND id = ANY($2::uuid[]) AND deleted_at IS NULL"
        if table == "spaces"
        else "SELECT id FROM assets WHERE user_id = $1 AND id = ANY($2::uuid[]) AND status = 'uploaded'"
    )
    rows = await fetch(sql, user_id, _uuids(values))
    return len(rows) == len(values)


def _encode_cursor(captured_at: dt.datetime, memory_id: str) -> str:
    raw = f"{iso_milliseconds(captured_at)}|{memory_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(value: str | None) -> tuple[dt.datetime, str] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    separator = decoded.rfind("|")
    if separator < 0:
        return None
    memory_id = decoded[separator + 1 :]
    if not _MEMORY_ID.match(memory_id):
        return None
    try:
        captured_at = parse_timestamp(decoded[:separator])
    except ApiError:
        return None
    return (captured_at, memory_id) if captured_at else None


async def _get_memory(
    user_id: uuid.UUID, memory_id: uuid.UUID, *, record_opened: bool = False
) -> dict[str, Any] | None:
    memory = await fetchrow(
        """WITH target AS MATERIALIZED (
           SELECT m.id, m.kind, m.status, m.processing_error, m.source_app, m.source_url, m.source_domain,
             m.title, m.description, m.user_note, m.content_text, m.page_text,
             m.capture_metadata, m.captured_at, m.occurred_at, m.created_at, m.updated_at,
             COALESCE((SELECT json_agg(json_build_object('id',s.id,'name',s.name,'color',s.color,'icon',s.icon) ORDER BY s.name)
               FROM memory_spaces ms JOIN spaces s ON s.id=ms.space_id AND s.deleted_at IS NULL
               WHERE ms.memory_id=m.id AND ms.user_id=m.user_id), '[]'::json) AS spaces
           FROM memories m WHERE m.id=$1 AND m.user_id=$2 AND m.deleted_at IS NULL
         ), opened AS (
           UPDATE memories m SET last_opened_at=now()
           FROM target t
           WHERE $3::boolean AND m.id=t.id AND m.user_id=$2 AND m.deleted_at IS NULL
           RETURNING m.id, m.user_id
         ), opened_event AS (
           INSERT INTO memory_events(user_id,memory_id,event_type)
           SELECT o.user_id,o.id,'opened' FROM opened o
           RETURNING memory_id
         )
         SELECT t.*,
           COALESCE((SELECT json_agg(json_build_object('id',a.id,'filename',a.original_filename,
             'mimeType',a.mime_type,'byteSize',a.byte_size,'status',a.status,'createdAt',a.created_at,'role',ma.role)
             ORDER BY ma.position)
             FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id AND a.user_id=ma.user_id
             WHERE ma.memory_id=t.id AND ma.user_id=$2), '[]'::json) AS assets
         FROM target t""",
        memory_id,
        user_id,
        record_opened,
    )
    if memory is None:
        return None
    return {
        **memory_card(memory),
        "processingError": memory["processing_error"],
        "description": memory["description"],
        "userNote": memory["user_note"],
        "contentText": memory["content_text"],
        "pageText": memory["page_text"],
        "captureMetadata": memory["capture_metadata"],
        "occurredAt": memory["occurred_at"],
        "createdAt": memory["created_at"],
        "updatedAt": memory["updated_at"],
        "spaces": memory["spaces"],
        "assets": [
            {
                "id": str(asset["id"]),
                "filename": asset["filename"],
                "mimeType": asset["mimeType"],
                "byteSize": int(asset["byteSize"]) if asset["byteSize"] is not None else None,
                "status": asset["status"],
                "role": asset["role"],
                "createdAt": asset["createdAt"],
                "url": f"/v1/assets/{asset['id']}/content",
            }
            for asset in memory["assets"]
        ],
    }


@router.post("/memories")
async def create_memory(request: Request, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    payload = await parse_body(CreateMemoryRequest, request, "invalid_memory", "Invalid Memory.")
    user_id = uuid.UUID(principal.id)
    header = request.headers.get("idempotency-key")
    idempotency_key = header.strip()[:128] if header else None
    if idempotency_key:
        existing = await fetchrow(
            "SELECT id FROM memories WHERE user_id=$1 AND idempotency_key=$2 AND deleted_at IS NULL",
            user_id,
            idempotency_key,
        )
        if existing:
            memory = await _get_memory(user_id, existing["id"])
            return respond({"memory": memory, "duplicate": True})
    if not await _validate_owned_ids(user_id, payload.spaceIds, "spaces"):
        raise ApiError(400, "invalid_space", "One or more Spaces do not belong to this account.")
    if not await _validate_owned_ids(user_id, payload.assetIds, "assets"):
        raise ApiError(400, "invalid_asset", "One or more uploads are unavailable or not complete.")

    captured_at = parse_timestamp(payload.capturedAt)
    raced_memory_id: Any = None
    async with transaction() as connection:
        inserted = await connection.fetchrow(
            """INSERT INTO memories(user_id, kind, status, source_app, source_url, source_domain, title, description,
                user_note, content_text, capture_metadata, captured_at, idempotency_key)
               VALUES($1,$2,'queued',$3,$4,$5,$6,$7,$8,$9,$10::jsonb,COALESCE($11::timestamptz,now()),$12)
               ON CONFLICT (user_id,idempotency_key) DO NOTHING RETURNING id""",
            user_id,
            payload.kind.value,
            payload.sourceApp,
            payload.sourceUrl,
            source_domain(payload.sourceUrl),
            payload.title,
            payload.description,
            payload.userNote,
            payload.contentText,
            payload.captureMetadata,
            captured_at,
            idempotency_key,
        )
        if inserted is None:
            raced = await connection.fetchrow(
                "SELECT id FROM memories WHERE user_id=$1 AND idempotency_key=$2 AND deleted_at IS NULL",
                user_id,
                idempotency_key,
            )
            if raced is None:
                raise ApiError(500, "internal_error", "The request could not be completed.")
            raced_memory_id = raced["id"]
        else:
            memory_id = inserted["id"]
            space_ids = _unique(payload.spaceIds)
            if space_ids:
                await connection.execute(
                    """INSERT INTO memory_spaces(memory_id, space_id, user_id, assigned_by)
                       SELECT $1, id, $2, 'user' FROM spaces WHERE id=ANY($3::uuid[]) AND user_id=$2 AND deleted_at IS NULL""",
                    memory_id,
                    user_id,
                    _uuids(space_ids),
                )
            asset_ids = _unique(payload.assetIds)
            if asset_ids:
                await connection.execute(
                    """INSERT INTO memory_assets(memory_id, asset_id, user_id, role, position)
                       SELECT $1, id, $2, CASE WHEN position=1 THEN 'original' ELSE 'attachment' END, position-1
                       FROM unnest($3::uuid[]) WITH ORDINALITY AS input(id, position)
                       WHERE EXISTS (SELECT 1 FROM assets a WHERE a.id=input.id AND a.user_id=$2 AND a.status='uploaded')""",
                    memory_id,
                    user_id,
                    _uuids(asset_ids),
                )
                await connection.execute(
                    "UPDATE assets SET status='attached' WHERE id=ANY($1::uuid[]) AND user_id=$2",
                    _uuids(asset_ids),
                    user_id,
                )
            await enqueue_memory_processing(connection, user_id, [str(memory_id)])

    if raced_memory_id is not None:
        return respond({"memory": await _get_memory(user_id, raced_memory_id), "duplicate": True})
    return respond({"memory": await _get_memory(user_id, memory_id)}, 201)


@router.get("/memories")
async def list_memories(request: Request, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    return respond(await list_memories_for_user(principal, request.query_params))


async def list_memories_for_user(principal: Principal, query: Mapping[str, str]) -> dict[str, Any]:
    """List one caller's memories from plain query values, shared by HTTP and MCP."""
    limit = parse_limit(query.get("limit"), default=LIST_DEFAULT_LIMIT, minimum=LIST_MIN_LIMIT, maximum=LIST_MAX_LIMIT)
    kind = parse_kind_param(query.get("kind"))
    raw_cursor = query.get("cursor")
    cursor = _decode_cursor(raw_cursor)
    if raw_cursor and cursor is None:
        raise ApiError(400, "invalid_cursor", "The page cursor is invalid.")
    after = parse_timestamp(query.get("after")) if query.get("after") else None
    before = parse_timestamp(query.get("before")) if query.get("before") else None
    user_id = uuid.UUID(principal.id)
    space_id = query.get("spaceId")
    rows = await fetch(
        f"""SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
            m.description, m.user_note, m.page_text, m.captured_at, m.created_at,
            {PREVIEW_KEY_SUBQUERY}
           FROM memories m
           WHERE m.user_id=$1 AND m.deleted_at IS NULL
             AND ($2::memory_kind IS NULL OR m.kind=$2::memory_kind)
             AND ($3::uuid IS NULL OR EXISTS (SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$3 AND ms.user_id=m.user_id))
             AND ($4::text IS NULL OR m.source_domain=$4)
             AND ($5::timestamptz IS NULL OR (m.captured_at,m.id)<($5::timestamptz,$6::uuid))
             AND ($8::timestamptz IS NULL OR m.captured_at >= $8::timestamptz)
             AND ($9::timestamptz IS NULL OR m.captured_at < $9::timestamptz)
           ORDER BY m.captured_at DESC, m.id DESC LIMIT $7""",
        user_id,
        kind,
        as_uuid(space_id) if space_id else None,
        query.get("source"),
        cursor[0] if cursor else None,
        uuid.UUID(cursor[1]) if cursor else None,
        limit + 1,
        after,
        before,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    items = [
        {
            **memory_card(row),
            "description": row["description"],
            "userNote": row["user_note"],
            "pageText": row["page_text"],
            "createdAt": row["created_at"],
            "previewUrl": f"/v1/memories/{row['id']}/preview" if row["preview_key"] else None,
        }
        for row in page
    ]
    last = page[-1] if page else None
    return {
        "memories": items,
        "nextCursor": _encode_cursor(last["captured_at"], str(last["id"])) if has_more and last else None,
    }


@router.get("/memories/{memory_id}")
async def get_memory(memory_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    user_id = uuid.UUID(principal.id)
    started = time.perf_counter()
    memory = await _get_memory(user_id, as_uuid(memory_id), record_opened=True)
    logger.info("memory_open elapsed_ms=%.1f found=%s", (time.perf_counter() - started) * 1000, memory is not None)
    if memory is None:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    return respond({"memory": memory})


async def get_memory_detail(
    memory_id: str,
    principal: Principal,
    *,
    record_opened: bool = False,
) -> dict[str, Any]:
    """Read one caller-owned memory, optionally recording an in-app open event."""
    user_id = uuid.UUID(principal.id)
    memory = await _get_memory(user_id, as_uuid(memory_id), record_opened=record_opened)
    if memory is None:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    return memory


@router.patch("/memories/{memory_id}")
async def update_memory(
    request: Request, memory_id: str, principal: Principal = Depends(require_auth)
) -> ApiJSONResponse:
    payload = await parse_body(UpdateMemoryRequest, request, "invalid_memory_update", "Invalid update.")
    user_id = uuid.UUID(principal.id)
    if payload.spaceIds is not None and not await _validate_owned_ids(user_id, payload.spaceIds, "spaces"):
        raise ApiError(400, "invalid_space", "One or more Spaces do not belong to this account.")
    target = as_uuid(memory_id)
    async with transaction() as connection:
        updated = await connection.fetchrow(
            """UPDATE memories SET title=CASE WHEN $3 THEN $4 ELSE title END,
                user_note=CASE WHEN $5 THEN $6 ELSE user_note END, updated_at=now()
             WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL RETURNING id""",
            target,
            user_id,
            "title" in payload.model_fields_set,
            payload.title,
            "userNote" in payload.model_fields_set,
            payload.userNote,
        )
        if updated is None:
            raise ApiError(404, "memory_not_found", "Memory not found.")
        if payload.spaceIds is not None:
            await connection.execute("DELETE FROM memory_spaces WHERE memory_id=$1 AND user_id=$2", target, user_id)
            space_ids = _unique(payload.spaceIds)
            if space_ids:
                await connection.execute(
                    """INSERT INTO memory_spaces(memory_id,space_id,user_id,assigned_by)
                       SELECT $1,id,$2,'user' FROM spaces WHERE id=ANY($3::uuid[]) AND user_id=$2 AND deleted_at IS NULL""",
                    target,
                    user_id,
                    _uuids(space_ids),
                )
    return respond({"memory": await _get_memory(user_id, target)})


@router.post("/memories/{memory_id}/move")
async def move_memory(
    request: Request, memory_id: str, principal: Principal = Depends(require_auth)
) -> ApiJSONResponse:
    payload = await parse_body(
        MoveMemoryRequest, request, "invalid_memory_move", "Choose a source and destination Space."
    )
    user_id, target = uuid.UUID(principal.id), as_uuid(memory_id)
    async with transaction() as connection:
        memory = await connection.fetchrow(
            "SELECT id FROM memories WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL FOR UPDATE",
            target,
            user_id,
        )
        if memory is None:
            raise ApiError(404, "memory_not_found", "Memory not found.")
        spaces = await connection.fetch(
            "SELECT id FROM spaces WHERE user_id=$1 AND id=ANY($2::uuid[]) AND deleted_at IS NULL ORDER BY id FOR SHARE",
            user_id,
            [payload.fromSpaceId, payload.toSpaceId],
        )
        if len(spaces) != 2:
            raise ApiError(400, "invalid_space", "The source or destination Space is unavailable.")
        removed = await connection.fetchrow(
            "DELETE FROM memory_spaces WHERE memory_id=$1 AND user_id=$2 AND space_id=$3 RETURNING memory_id",
            target,
            user_id,
            payload.fromSpaceId,
        )
        if removed is None:
            destination = await connection.fetchrow(
                "SELECT memory_id FROM memory_spaces WHERE memory_id=$1 AND user_id=$2 AND space_id=$3",
                target,
                user_id,
                payload.toSpaceId,
            )
            if destination is None:
                raise ApiError(409, "memory_space_changed", "This memory is no longer in the source Space.")
        await connection.execute(
            """INSERT INTO memory_spaces(memory_id,space_id,user_id,assigned_by) VALUES($1,$2,$3,'user')
               ON CONFLICT(memory_id,space_id) DO UPDATE SET assigned_by='user'""",
            target,
            payload.toSpaceId,
            user_id,
        )
        await connection.execute("UPDATE memories SET updated_at=now() WHERE id=$1 AND user_id=$2", target, user_id)
    detail = await _get_memory(user_id, target)
    if detail is None:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    return respond({"memory": detail})


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, principal: Principal = Depends(require_auth)) -> Response:
    user_id = uuid.UUID(principal.id)
    deleted = await fetchrow(
        "UPDATE memories SET deleted_at=now(), updated_at=now() WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL RETURNING id",
        as_uuid(memory_id),
        user_id,
    )
    if deleted is None:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    return Response(status_code=204)


@router.post("/memories/{memory_id}/restore")
async def restore_memory(memory_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    user_id = uuid.UUID(principal.id)
    target = as_uuid(memory_id)
    async with transaction() as connection:
        await connection.execute(
            "SELECT memory_id FROM memory_processing_jobs WHERE memory_id=$1 AND user_id=$2 FOR UPDATE",
            target,
            user_id,
        )
        result = await connection.fetchrow(
            "UPDATE memories SET deleted_at=NULL, updated_at=now() WHERE id=$1 AND user_id=$2 AND deleted_at IS NOT NULL RETURNING status",
            target,
            user_id,
        )
        if result is None:
            raise ApiError(404, "deleted_memory_not_found", "Deleted Memory not found.")
        if result["status"] in (MemoryStatus.QUEUED, MemoryStatus.PROCESSING):
            await connection.execute(
                "UPDATE memories SET status='queued', processing_error=NULL WHERE id=$1 AND user_id=$2",
                target,
                user_id,
            )
            await enqueue_memory_processing(connection, user_id, [memory_id])
    return respond({"memory": await _get_memory(user_id, target)})


@router.post("/memories/{memory_id}/retry")
async def retry_memory(memory_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    user_id = uuid.UUID(principal.id)
    target = as_uuid(memory_id)
    async with transaction() as connection:
        await connection.execute(
            "SELECT memory_id FROM memory_processing_jobs WHERE memory_id=$1 AND user_id=$2 FOR UPDATE",
            target,
            user_id,
        )
        result = await connection.fetchrow(
            "UPDATE memories SET status='queued', processing_error=NULL WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL AND status='failed' RETURNING id",
            target,
            user_id,
        )
        if result is None:
            raise ApiError(409, "memory_not_retryable", "Only failed Memories can be retried.")
        await enqueue_memory_processing(connection, user_id, [memory_id])
    return respond({"memory": await _get_memory(user_id, target)})
