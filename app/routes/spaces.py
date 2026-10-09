"""Space CRUD."""

from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Self

import asyncpg
from fastapi import APIRouter, Depends, Request, Response

from app.auth import AUTH_SUBJECT_CTE, VerifiedSubject, as_uuid, require_subject, resolve_auth_state
from app.db import fetch, fetchrow
from app.errors import ApiError, ApiJSONResponse, respond
from app.schemas import CreateSpaceRequest, UpdateSpaceRequest, parse_body
from app.serialize import Row, WireModel

logger = logging.getLogger("trove.spaces")

# No router-level auth dependency: every endpoint declares its own, so each read and write can
# verify the token without a database round trip and resolve the account inside its own query.
router = APIRouter()

_SPACE_COLUMNS = "id, name, description, color, icon, created_at, updated_at"


class Space(WireModel):
    """The Space shape every route returns.

    Field names are the client's; `from_row` is where they meet the columns.
    """

    id: str
    name: str
    description: str | None
    color: str | None
    icon: str | None
    createdAt: dt.datetime
    updatedAt: dt.datetime

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(
            id=str(row["id"]),
            name=row["name"],
            description=row["description"],
            color=row["color"],
            icon=row["icon"],
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
        )


class SpaceWithMemoryCount(Space):
    """A listed Space plus its live Memory count, which only the list query's join produces.

    Naming it in a separate model is what stops a create or patch response from carrying a count it
    never read; the client's field is optional, so absence is a shape the type can express.
    """

    memoryCount: int

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(**Space.from_row(row).model_dump(), memoryCount=row["memory_count"])


@router.get("/spaces")
async def list_spaces(subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    return respond(await list_spaces_for_user(subject))


async def list_spaces_for_user(subject: VerifiedSubject) -> dict[str, list[SpaceWithMemoryCount]]:
    """List a caller's Spaces for the HTTP route and MCP tools.

    The account resolution shares the list query's round trip: the auth anchor always yields at
    least one row, so a caller with no Spaces still gets their auth outcome instead of silence.
    """
    rows = await fetch(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT a.deleted, a.deletion_pending, a.user_id, listed.*
            FROM auth a
            LEFT JOIN LATERAL (
              SELECT s.id, s.name, s.description, s.color, s.icon, s.created_at, s.updated_at,
                count(m.id)::int AS memory_count
              FROM spaces s LEFT JOIN memory_spaces ms ON ms.space_id = s.id AND ms.user_id = s.user_id
              LEFT JOIN memories m ON m.id = ms.memory_id AND m.deleted_at IS NULL
              WHERE s.user_id = a.user_id AND s.deleted_at IS NULL
              GROUP BY s.id ORDER BY s.created_at ASC
            ) listed ON NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL""",
        subject.subject,
        subject.email,
        subject.display_name,
    )
    if not rows:  # pragma: no cover - the auth anchor always yields at least one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(rows[0])
    return {"spaces": [SpaceWithMemoryCount.from_row(row) for row in rows if row["id"] is not None]}


@router.post("/spaces")
async def create_space(request: Request, subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    payload = await parse_body(CreateSpaceRequest, request, "invalid_request", "Invalid Space.")
    started = time.perf_counter()
    try:
        space = await fetchrow(
            f"""WITH {AUTH_SUBJECT_CTE}, created AS (
                 INSERT INTO spaces(user_id, name, description, color, icon)
                 SELECT user_id, $4, $5, $6, $7 FROM auth
                 WHERE NOT deleted AND NOT deletion_pending AND user_id IS NOT NULL
                 RETURNING {_SPACE_COLUMNS}
               )
               SELECT a.deleted, a.deletion_pending, a.user_id, created.*
               FROM auth a LEFT JOIN created ON TRUE""",
            subject.subject,
            subject.email,
            subject.display_name,
            payload.name,
            payload.description,
            payload.color,
            payload.icon,
        )
    except asyncpg.UniqueViolationError as error:
        raise ApiError(409, "space_name_exists", "A Space with that name already exists.") from error
    if space is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(space)
    if space["id"] is None:  # pragma: no cover - the gates above insert whenever auth passes
        raise ApiError(500, "internal_error", "The request could not be completed.")
    logger.info("space_created space_id=%s elapsed_ms=%.1f", space["id"], (time.perf_counter() - started) * 1000)
    return respond({"space": Space.from_row(space)}, 201)


@router.patch("/spaces/{space_id}")
async def update_space(
    request: Request, space_id: str, subject: VerifiedSubject = Depends(require_subject)
) -> ApiJSONResponse:
    payload = await parse_body(UpdateSpaceRequest, request, "invalid_request", "Invalid Space.")
    return respond({"space": await update_space_for_user(space_id, subject, payload)})


async def update_space_for_user(space_id: str, subject: VerifiedSubject, payload: UpdateSpaceRequest) -> Space:
    """Update an owned Space from validated domain input, shared by HTTP and MCP."""
    fields = payload.model_fields_set
    try:
        space = await fetchrow(
            f"""WITH {AUTH_SUBJECT_CTE}, updated AS (
                 UPDATE spaces s SET name = COALESCE($4,name),
                   description = CASE WHEN $5 THEN $6 ELSE description END,
                   color = CASE WHEN $7 THEN $8 ELSE color END,
                   icon = CASE WHEN $9 THEN $10 ELSE icon END, updated_at = now()
                 FROM auth a
                 WHERE s.id = $11 AND s.user_id = a.user_id AND s.deleted_at IS NULL
                   AND NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL
                 RETURNING {_SPACE_COLUMNS}
               )
               SELECT a.deleted, a.deletion_pending, a.user_id, updated.*
               FROM auth a LEFT JOIN updated ON TRUE""",
            subject.subject,
            subject.email,
            subject.display_name,
            payload.name,
            "description" in fields,
            payload.description,
            "color" in fields,
            payload.color,
            "icon" in fields,
            payload.icon,
            as_uuid(space_id),
        )
    except asyncpg.UniqueViolationError as error:
        raise ApiError(409, "space_name_exists", "A Space with that name already exists.") from error
    if space is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(space)
    if space["id"] is None:
        raise ApiError(404, "space_not_found", "Space not found.")
    return Space.from_row(space)


@router.delete("/spaces/{space_id}", status_code=204)
async def delete_space(space_id: str, subject: VerifiedSubject = Depends(require_subject)) -> Response:
    deleted = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}, removed AS (
             UPDATE spaces s SET deleted_at = now(), updated_at = now() FROM auth a
             WHERE s.id = $4 AND s.user_id = a.user_id AND s.deleted_at IS NULL
               AND NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL
             RETURNING s.id
           )
           SELECT a.deleted, a.deletion_pending, a.user_id, removed.id
           FROM auth a LEFT JOIN removed ON TRUE""",
        subject.subject,
        subject.email,
        subject.display_name,
        as_uuid(space_id),
    )
    if deleted is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(deleted)
    if deleted["id"] is None:
        raise ApiError(404, "space_not_found", "Space not found.")
    return Response(status_code=204)
