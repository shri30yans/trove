"""Space CRUD."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, Request, Response

from app.auth import Principal, as_uuid, require_auth
from app.db import fetch, fetchrow
from app.errors import ApiError, ApiJSONResponse, respond
from app.schemas import CreateSpaceRequest, UpdateSpaceRequest, parse_body

logger = logging.getLogger("trove.spaces")

router = APIRouter(dependencies=[Depends(require_auth)])

_SPACE_COLUMNS = "id, name, description, color, icon, created_at, updated_at"


def _as_space(row: dict[str, Any]) -> dict[str, Any]:
    """The one Space wire shape. memory_count only exists on the list query's join, so a create or
    update reports no count rather than a guessed one; the client's field is optional."""
    space = {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "color": row["color"],
        "icon": row["icon"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if "memory_count" in row:
        space["memoryCount"] = row["memory_count"]
    return space


@router.get("/spaces")
async def list_spaces(principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    return respond(await list_spaces_for_user(principal))


async def list_spaces_for_user(principal: Principal) -> dict[str, Any]:
    """List a caller's Spaces for the HTTP route and MCP tools."""
    rows = await fetch(
        """SELECT s.id, s.name, s.description, s.color, s.icon, s.created_at, s.updated_at,
            count(ms.memory_id)::int AS memory_count
           FROM spaces s LEFT JOIN memory_spaces ms ON ms.space_id = s.id AND ms.user_id = s.user_id
           LEFT JOIN memories m ON m.id = ms.memory_id AND m.deleted_at IS NULL
           WHERE s.user_id = $1 AND s.deleted_at IS NULL
           GROUP BY s.id ORDER BY s.created_at ASC""",
        uuid.UUID(principal.id),
    )
    return {"spaces": [_as_space(row) for row in rows]}


@router.post("/spaces")
async def create_space(request: Request, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    payload = await parse_body(CreateSpaceRequest, request, "invalid_request", "Invalid Space.")
    started = time.perf_counter()
    try:
        space = await fetchrow(
            f"INSERT INTO spaces(user_id, name, description, color, icon) VALUES($1,$2,$3,$4,$5) RETURNING {_SPACE_COLUMNS}",
            uuid.UUID(principal.id),
            payload.name,
            payload.description,
            payload.color,
            payload.icon,
        )
    except asyncpg.UniqueViolationError as error:
        raise ApiError(409, "space_name_exists", "A Space with that name already exists.") from error
    if space is None:
        raise ApiError(500, "internal_error", "The request could not be completed.")
    logger.info("space_created space_id=%s elapsed_ms=%.1f", space["id"], (time.perf_counter() - started) * 1000)
    return respond({"space": _as_space(space)}, 201)


@router.patch("/spaces/{space_id}")
async def update_space(
    request: Request, space_id: str, principal: Principal = Depends(require_auth)
) -> ApiJSONResponse:
    payload = await parse_body(UpdateSpaceRequest, request, "invalid_request", "Invalid Space.")
    return respond({"space": await update_space_for_user(space_id, principal, payload)})


async def update_space_for_user(space_id: str, principal: Principal, payload: UpdateSpaceRequest) -> dict[str, Any]:
    """Update an owned Space from validated domain input, shared by HTTP and MCP."""
    fields = payload.model_fields_set
    try:
        space = await fetchrow(
            f"""UPDATE spaces SET name = COALESCE($3,name), description = CASE WHEN $4 THEN $5 ELSE description END,
                  color = CASE WHEN $6 THEN $7 ELSE color END, icon = CASE WHEN $8 THEN $9 ELSE icon END, updated_at = now()
                WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL
                RETURNING {_SPACE_COLUMNS}""",
            as_uuid(space_id),
            uuid.UUID(principal.id),
            payload.name,
            "description" in fields,
            payload.description,
            "color" in fields,
            payload.color,
            "icon" in fields,
            payload.icon,
        )
    except asyncpg.UniqueViolationError as error:
        raise ApiError(409, "space_name_exists", "A Space with that name already exists.") from error
    if space is None:
        raise ApiError(404, "space_not_found", "Space not found.")
    return _as_space(space)


@router.delete("/spaces/{space_id}", status_code=204)
async def delete_space(space_id: str, principal: Principal = Depends(require_auth)) -> Response:
    deleted = await fetchrow(
        "UPDATE spaces SET deleted_at = now(), updated_at = now() WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL RETURNING id",
        as_uuid(space_id),
        uuid.UUID(principal.id),
    )
    if deleted is None:
        raise ApiError(404, "space_not_found", "Space not found.")
    return Response(status_code=204)
