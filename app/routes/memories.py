"""Creating and editing a Memory, and reading one back."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request

from app.auth import Principal, as_uuid, require_auth
from app.db import current_request_id, fetch, fetchrow, transaction
from app.errors import ApiError, ApiJSONResponse, respond
from app.memory_reads import get_memory_detail, list_memories_for_user, read_back
from app.queue import enqueue_memory_processing
from app.schemas import CreateMemoryRequest, UpdateMemoryRequest, parse_body, source_domain
from app.times import parse_timestamp

router = APIRouter(dependencies=[Depends(require_auth)])
logger = logging.getLogger("trove.api")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _uuids(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(value) for value in values]


async def _owns_all(user_id: uuid.UUID, ids: list[str], table: str) -> bool:
    """Whether every id is this account's to attach: an undeleted Space or a completed upload.

    A write that goes through this check repeats the same predicate inside its own transaction, so a
    row deleted in between is dropped rather than attached.
    """
    values = _unique(ids)
    if not values:
        return True
    sql = (
        "SELECT id FROM spaces WHERE user_id = $1 AND id = ANY($2::uuid[]) AND deleted_at IS NULL"
        if table == "spaces"
        else "SELECT id FROM assets WHERE user_id = $1 AND id = ANY($2::uuid[]) AND status = 'uploaded'"
    )
    return len(await fetch(sql, user_id, _uuids(values))) == len(values)


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
            return respond({"memory": await read_back(user_id, existing["id"]), "duplicate": True})
    if not await _owns_all(user_id, payload.spaceIds, "spaces"):
        raise ApiError(400, "invalid_space", "One or more Spaces do not belong to this account.")
    if not await _owns_all(user_id, payload.assetIds, "assets"):
        raise ApiError(400, "invalid_asset", "One or more uploads are unavailable or not complete.")

    captured_at = parse_timestamp(payload.capturedAt)
    raced_memory_id: uuid.UUID | None = None
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
        return respond({"memory": await read_back(user_id, raced_memory_id), "duplicate": True})
    return respond({"memory": await read_back(user_id, memory_id)}, 201)


@router.get("/memories")
async def list_memories(request: Request, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    return respond(await list_memories_for_user(principal, request.query_params))


@router.get("/memory-tags")
async def list_memory_tags(request: Request, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    """List this account's tags for memory-tag autocomplete."""
    query = (request.query_params.get("q") or "").strip().lower()
    if len(query) > 40:
        raise ApiError(400, "invalid_tag", "Tag search must be 40 characters or fewer.")
    tags = await fetch(
        """SELECT tag, count(*)::int AS memory_count FROM memory_tags
           WHERE user_id=$1 AND ($2::text='' OR tag LIKE '%' || $2 || '%')
           GROUP BY tag ORDER BY memory_count DESC, tag LIMIT 50""",
        uuid.UUID(principal.id),
        query,
    )
    return respond({"tags": [{"tag": row["tag"], "memoryCount": row["memory_count"]} for row in tags]})


@router.get("/memories/{memory_id}")
async def get_memory(memory_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    started = time.perf_counter()
    memory = await get_memory_detail(memory_id, principal, record_opened=True)
    logger.info(
        "memory_open request_id=%s elapsed_ms=%.1f", current_request_id(), (time.perf_counter() - started) * 1000
    )
    return respond({"memory": memory})


@router.patch("/memories/{memory_id}")
async def update_memory(
    request: Request, memory_id: str, principal: Principal = Depends(require_auth)
) -> ApiJSONResponse:
    payload = await parse_body(UpdateMemoryRequest, request, "invalid_memory_update", "Invalid update.")
    user_id = uuid.UUID(principal.id)
    if payload.spaceIds is not None and not await _owns_all(user_id, payload.spaceIds, "spaces"):
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
        if "tags" in payload.model_fields_set:
            await connection.execute("DELETE FROM memory_tags WHERE memory_id=$1 AND user_id=$2", target, user_id)
            if payload.tags:
                await connection.execute(
                    """INSERT INTO memory_tags(memory_id,user_id,tag)
                       SELECT m.id,m.user_id,tag FROM memories m CROSS JOIN unnest($3::text[]) AS tag
                       WHERE m.id=$1 AND m.user_id=$2 AND m.deleted_at IS NULL""",
                    target,
                    user_id,
                    payload.tags,
                )
    return respond({"memory": await read_back(user_id, target)})
