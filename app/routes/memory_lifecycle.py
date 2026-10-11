"""What happens to a Memory after it is stored: trashing, recovery, and Space placement.

These operations all begin with a Memory the account already owns and answer by moving it to another
state rather than by editing its content. Each one owns its transaction end to end, and each holds
back the queue until the row it changed is committed, so a retry never re-enqueues work the database
did not accept.
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import APIRouter, Depends, Request, Response

from app.auth import (
    AUTH_SUBJECT_CTE,
    Principal,
    VerifiedSubject,
    as_uuid,
    require_auth,
    require_subject,
    resolve_auth_state,
)
from app.db import fetchrow, transaction
from app.domain.enums import MemoryStatus
from app.errors import ApiError, ApiJSONResponse, respond
from app.memory_reads import read_back
from app.queue import enqueue_memory_processing
from app.schemas import MoveMemoryRequest, parse_body

router = APIRouter()


async def _lock_processing_job(
    connection: asyncpg.Connection,
    user_id: uuid.UUID,
    memory_id: uuid.UUID,
) -> None:
    """Serialize this Memory's processing with whatever the worker is doing to it.

    Taking the job row before changing the Memory is what stops a restore or retry from re-enqueuing a
    Memory the worker is mid-way through, which would double-process it.
    """
    await connection.execute(
        "SELECT memory_id FROM memory_processing_jobs WHERE memory_id=$1 AND user_id=$2 FOR UPDATE",
        memory_id,
        user_id,
    )


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, subject: VerifiedSubject = Depends(require_subject)) -> Response:
    deleted = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}, removed AS (
             UPDATE memories m SET deleted_at=now(), updated_at=now() FROM auth a
             WHERE m.id=$4 AND m.user_id=a.user_id AND m.deleted_at IS NULL
               AND NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL
             RETURNING m.id
           )
           SELECT a.deleted, a.deletion_pending, a.user_id, removed.id
           FROM auth a LEFT JOIN removed ON TRUE""",
        subject.subject,
        subject.email,
        subject.display_name,
        as_uuid(memory_id),
    )
    if deleted is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(deleted)
    if deleted["id"] is None:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    return Response(status_code=204)


@router.post("/memories/{memory_id}/restore")
async def restore_memory(memory_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    user_id = uuid.UUID(principal.id)
    target = as_uuid(memory_id)
    async with transaction() as connection:
        await _lock_processing_job(connection, user_id, target)
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
    return respond({"memory": await read_back(user_id, target)})


@router.post("/memories/{memory_id}/retry")
async def retry_memory(memory_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    user_id = uuid.UUID(principal.id)
    target = as_uuid(memory_id)
    async with transaction() as connection:
        await _lock_processing_job(connection, user_id, target)
        result = await connection.fetchrow(
            "UPDATE memories SET status='queued', processing_error=NULL WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL AND status='failed' RETURNING id",
            target,
            user_id,
        )
        if result is None:
            raise ApiError(409, "memory_not_retryable", "Only failed Memories can be retried.")
        await enqueue_memory_processing(connection, user_id, [memory_id])
    return respond({"memory": await read_back(user_id, target)})


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
            # Idempotent retry: the membership may already have moved, in which case arriving at the
            # destination again is success, not a conflict.
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
    return respond({"memory": await read_back(user_id, target)})
