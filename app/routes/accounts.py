"""Account, preferences, explore, and resurfacing endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.auth import Principal, require_auth
from app.db import fetch, fetchrow, transaction
from app.domain.enums import ResurfacingCadence
from app.domain.plans import storage_plan_payload
from app.embedding import embeddings
from app.errors import ApiError, ApiJSONResponse, respond
from app.schemas import UpdatePreferencesRequest, parse_body
from app.vector_search import find_resurfacing_memories

router = APIRouter(dependencies=[Depends(require_auth)])


def _preferences_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    base = {
        "resurfacingEnabled": False,
        "resurfacingCadence": ResurfacingCadence.WEEKLY,
        "embeddingsEnabled": False,
    }
    if row is not None:
        base = {
            "resurfacingEnabled": row["resurfacing_enabled"],
            "resurfacingCadence": row["resurfacing_cadence"],
            "embeddingsEnabled": row["embeddings_enabled"],
            "updatedAt": row["updated_at"],
        }
    base["embeddingsAvailable"] = embeddings.is_ready()
    return base


@router.get("/me")
async def me(principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    return respond({"user": principal.model_dump()})


@router.get("/plan")
async def get_plan(principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    row = await fetchrow(
        """SELECT u.storage_plan, COALESCE(SUM(a.byte_size), 0)::bigint AS storage_used_bytes
           FROM app_users u
           LEFT JOIN assets a ON a.user_id=u.id AND a.status IN ('pending_upload','uploaded','attached')
           WHERE u.id=$1 GROUP BY u.storage_plan""",
        uuid.UUID(principal.id),
    )
    if row is None:
        raise ApiError(500, "account_not_found", "The account plan could not be loaded.")
    try:
        plan = storage_plan_payload(row["storage_plan"], int(row["storage_used_bytes"]))
    except ValueError as error:
        raise ApiError(500, "invalid_storage_plan", "The account plan is not supported.") from error
    return respond({"plan": plan})


@router.get("/processing")
async def processing_summary(principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    """Whole-library server-side processing counts; a paginated Memory list cannot answer this."""
    rows = await fetch(
        """SELECT status, count(*)::int AS memory_count
           FROM memories WHERE user_id=$1 AND deleted_at IS NULL GROUP BY status""",
        uuid.UUID(principal.id),
    )
    counts = {str(row["status"]): int(row["memory_count"]) for row in rows}
    return respond(
        {
            "processing": {
                "queued": counts.get("queued", 0),
                "processing": counts.get("processing", 0),
                "ready": counts.get("ready", 0),
                "failed": counts.get("failed", 0),
                "total": sum(counts.values()),
            }
        }
    )


@router.get("/preferences")
async def get_preferences(principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    row = await fetchrow(
        """SELECT resurfacing_enabled,resurfacing_cadence,embeddings_enabled,updated_at
           FROM user_preferences WHERE user_id=$1""",
        uuid.UUID(principal.id),
    )
    return respond({"preferences": _preferences_payload(row)})


@router.patch("/preferences")
async def patch_preferences(request: Request, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    """Persist the choice only; the worker's embedding reconcile converges the library on it."""
    payload = await parse_body(UpdatePreferencesRequest, request, "invalid_preferences", "Invalid preferences.")
    user_id = uuid.UUID(principal.id)

    async with transaction() as connection:
        row = await connection.fetchrow(
            """INSERT INTO user_preferences(user_id,resurfacing_enabled,resurfacing_cadence,embeddings_enabled)
               VALUES($1,CASE WHEN COALESCE($4,false) THEN COALESCE($2,false) ELSE false END,COALESCE($3,'weekly'),COALESCE($4,false))
               ON CONFLICT(user_id) DO UPDATE SET
                 resurfacing_enabled=CASE WHEN COALESCE($4,user_preferences.embeddings_enabled) THEN COALESCE($2,user_preferences.resurfacing_enabled) ELSE false END,
                 resurfacing_cadence=COALESCE($3,user_preferences.resurfacing_cadence),
                 embeddings_enabled=COALESCE($4,user_preferences.embeddings_enabled),updated_at=now()
               RETURNING resurfacing_enabled,resurfacing_cadence,embeddings_enabled,updated_at""",
            user_id,
            payload.resurfacingEnabled,
            payload.resurfacingCadence.value if payload.resurfacingCadence else None,
            payload.embeddingsEnabled,
        )

    return respond({"preferences": _preferences_payload(dict(row) if row else None)})


@router.get("/explore")
async def explore(principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    user_id = uuid.UUID(principal.id)
    months = await fetch(
        """SELECT date_trunc('month',captured_at)::date AS month, count(*)::int AS memory_count
           FROM memories WHERE user_id=$1 AND deleted_at IS NULL AND captured_at >= now()-interval '12 months'
           GROUP BY 1 ORDER BY 1 DESC LIMIT 12""",
        user_id,
    )
    return respond(
        {
            "months": [{"month": row["month"], "memoryCount": row["memory_count"]} for row in months],
        }
    )


@router.get("/updates")
async def updates(principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    user_id = uuid.UUID(principal.id)
    settings = await fetchrow(
        "SELECT resurfacing_enabled,resurfacing_cadence,embeddings_enabled FROM user_preferences WHERE user_id=$1",
        user_id,
    )
    cadence = settings["resurfacing_cadence"] if settings else ResurfacingCadence.WEEKLY
    if (
        settings is None
        or not settings["resurfacing_enabled"]
        or not settings["embeddings_enabled"]
        or cadence == ResurfacingCadence.OFF
    ):
        return respond({"enabled": False, "cadence": cadence, "updates": []})

    model_set = embeddings.models()
    if model_set is None:
        return respond({"enabled": True, "cadence": cadence, "updates": []})
    related = await find_resurfacing_memories(principal.id, model_set.space_id)
    if not related:
        return respond({"enabled": True, "cadence": cadence, "updates": []})

    rows = await fetch(
        """SELECT older.id, older.kind, older.source_app, older.source_url, older.source_domain, older.title,
            older.captured_at,
            recent.id AS related_id, recent.title AS related_title, recent.captured_at AS related_captured_at,
            matches.similarity,
            (SELECT a.object_key FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id
              WHERE ma.memory_id=older.id AND ma.user_id=older.user_id ORDER BY ma.position LIMIT 1) AS preview_key
           FROM unnest($2::uuid[],$3::uuid[],$4::float8[]) AS matches(memory_id,related_id,similarity)
           JOIN memories older ON older.id=matches.memory_id AND older.user_id=$1 AND older.deleted_at IS NULL
           JOIN memories recent ON recent.id=matches.related_id AND recent.user_id=$1 AND recent.deleted_at IS NULL
           ORDER BY matches.similarity DESC, older.captured_at DESC LIMIT 8""",
        user_id,
        [uuid.UUID(str(item["memoryId"])) for item in related],
        [uuid.UUID(str(item["relatedId"])) for item in related],
        [float(item["similarity"]) for item in related],
    )
    return respond(
        {
            "enabled": True,
            "cadence": cadence,
            "updates": [
                {
                    "memory": {
                        "id": str(row["id"]),
                        "kind": row["kind"],
                        "sourceApp": row["source_app"],
                        "sourceUrl": row["source_url"],
                        "sourceDomain": row["source_domain"],
                        "title": row["title"],
                        "capturedAt": row["captured_at"],
                        "previewUrl": f"/v1/memories/{row['id']}/preview" if row["preview_key"] else None,
                    },
                    "relatedTo": {
                        "id": str(row["related_id"]),
                        "title": row["related_title"],
                        "capturedAt": row["related_captured_at"],
                    },
                    "reason": "Related to a newer Memory in your Trove",
                    "similarity": float(row["similarity"]),
                }
                for row in rows
            ],
        }
    )
