"""Creating and editing a Memory, and reading one back."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request

from app.auth import (
    AUTH_SUBJECT_CTE,
    VerifiedSubject,
    as_uuid,
    require_subject,
    resolve_auth_state,
)
from app.db import current_request_id, fetch, fetchrow, transaction
from app.errors import ApiError, ApiJSONResponse, respond
from app.memory_reads import get_memory_detail_for_subject, list_memories_for_user, read_back
from app.queue import enqueue_memory_processing
from app.schemas import CreateMemoryRequest, UpdateMemoryRequest, parse_body, source_domain
from app.times import parse_timestamp

# No router-level auth dependency: every endpoint declares its own, so the open path can verify the
# token without a database round trip and resolve the account inside its read query instead.
router = APIRouter()
logger = logging.getLogger("trove.api")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _uuids(values: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(value) for value in values]


async def _ownership_standing(
    subject: VerifiedSubject,
    idempotency_key: str | None,
    space_ids: list[str],
    asset_ids: list[str],
) -> tuple[uuid.UUID, uuid.UUID | None, int, int]:
    """Resolve the caller, a duplicate save, and attachment ownership in one round trip.

    Returns the caller's id, the id of a live memory already saved under this idempotency
    key, and how many of the candidate Spaces and uploads are actually attachable. Comparing
    those counts against the de-duplicated request lists is what keeps a foreign id out.
    """
    row = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT (SELECT deleted FROM auth) AS deleted,
              (SELECT deletion_pending FROM auth) AS deletion_pending,
              (SELECT user_id FROM auth) AS user_id,
              (SELECT id FROM memories
               WHERE user_id=(SELECT user_id FROM auth) AND idempotency_key=$4 AND deleted_at IS NULL
              ) AS existing_id,
              (SELECT count(*)::int FROM spaces
               WHERE user_id=(SELECT user_id FROM auth) AND id=ANY($5::uuid[]) AND deleted_at IS NULL
              ) AS spaces_found,
              (SELECT count(*)::int FROM assets
               WHERE user_id=(SELECT user_id FROM auth) AND id=ANY($6::uuid[]) AND status='uploaded'
              ) AS assets_found
            FROM auth""",
        subject.subject,
        subject.email,
        subject.display_name,
        idempotency_key,
        _uuids(_unique(space_ids)),
        _uuids(_unique(asset_ids)),
    )
    if row is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    return resolve_auth_state(row), row["existing_id"], int(row["spaces_found"]), int(row["assets_found"])


@router.post("/memories")
async def create_memory(request: Request, subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    payload = await parse_body(CreateMemoryRequest, request, "invalid_memory", "Invalid Memory.")
    header = request.headers.get("idempotency-key")
    idempotency_key = header.strip()[:128] if header else None
    space_ids = _unique(payload.spaceIds)
    asset_ids = _unique(payload.assetIds)
    user_id, existing_id, spaces_found, assets_found = await _ownership_standing(
        subject, idempotency_key, space_ids, asset_ids
    )
    if idempotency_key and existing_id is not None:
        return respond({"memory": await read_back(user_id, existing_id), "duplicate": True})
    if spaces_found != len(space_ids):
        raise ApiError(400, "invalid_space", "One or more Spaces do not belong to this account.")
    if assets_found != len(asset_ids):
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
async def list_memories(request: Request, subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    return respond(await list_memories_for_user(subject, request.query_params))


@router.get("/memory-tags")
async def list_memory_tags(request: Request, subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    """List this account's tags for memory-tag autocomplete."""
    query = (request.query_params.get("q") or "").strip().lower()
    if len(query) > 40:
        raise ApiError(400, "invalid_tag", "Tag search must be 40 characters or fewer.")
    rows = await fetch(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT a.deleted, a.deletion_pending, a.user_id, matches.tag, matches.memory_count
            FROM auth a
            LEFT JOIN LATERAL (
              SELECT mt.tag, count(*)::int AS memory_count FROM memory_tags mt
              WHERE mt.user_id=a.user_id AND ($4::text='' OR mt.tag LIKE '%' || $4 || '%')
              GROUP BY mt.tag ORDER BY memory_count DESC, mt.tag LIMIT 50
            ) matches ON NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL""",
        subject.subject,
        subject.email,
        subject.display_name,
        query,
    )
    if not rows:  # pragma: no cover - the auth anchor always yields at least one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(rows[0])
    return respond(
        {"tags": [{"tag": row["tag"], "memoryCount": row["memory_count"]} for row in rows if row["tag"] is not None]}
    )


@router.get("/memories/{memory_id}")
async def get_memory(memory_id: str, subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    started = time.perf_counter()
    memory = await get_memory_detail_for_subject(memory_id, subject, record_opened=True)
    logger.info(
        "memory_open request_id=%s elapsed_ms=%.1f", current_request_id(), (time.perf_counter() - started) * 1000
    )
    return respond({"memory": memory})


@router.patch("/memories/{memory_id}")
async def update_memory(
    request: Request, memory_id: str, subject: VerifiedSubject = Depends(require_subject)
) -> ApiJSONResponse:
    payload = await parse_body(UpdateMemoryRequest, request, "invalid_memory_update", "Invalid update.")
    space_ids = _unique(payload.spaceIds) if payload.spaceIds is not None else []
    user_id, _, spaces_found, _ = await _ownership_standing(subject, None, space_ids, [])
    if payload.spaceIds is not None and spaces_found != len(space_ids):
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
