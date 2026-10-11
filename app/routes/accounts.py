"""Account, preferences, explore, and resurfacing endpoints."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Self

from fastapi import APIRouter, Depends, Request

from app.auth import AUTH_SUBJECT_CTE, Principal, VerifiedSubject, require_auth, require_subject, resolve_auth_state
from app.db import fetch, fetchrow
from app.domain.enums import MemoryKind, MemoryStatus, ResurfacingCadence
from app.domain.plans import StoragePlan, get_storage_plan
from app.domain.retrieval import RESURFACING_PAGE_SIZE
from app.embedding import embeddings
from app.errors import ApiError, ApiJSONResponse, respond
from app.queries import PREVIEW_KEY_SUBQUERY
from app.schemas import UpdatePreferencesRequest, parse_body
from app.serialize import Row, WireModel, preview_url
from app.vector_search import find_resurfacing_memories

router = APIRouter()


class PreferenceSettings(WireModel):
    """The choices in force.

    A user who has never saved a preference is in this shape: the API reports the defaults it applied
    and has no `updatedAt` to give, so the saved variant below adds the column rather than this model
    inventing one.
    """

    resurfacingEnabled: bool
    resurfacingCadence: ResurfacingCadence
    embeddingsEnabled: bool
    embeddingsAvailable: bool

    @classmethod
    def defaults(cls) -> Self:
        """What an account that has never saved a preference is told, read when the request is served."""
        return cls(
            resurfacingEnabled=False,
            resurfacingCadence=ResurfacingCadence.WEEKLY,
            embeddingsEnabled=False,
            embeddingsAvailable=embeddings.ready,
        )


class SavedPreferenceSettings(PreferenceSettings):
    """The same choices, read back from the row that stores them."""

    updatedAt: dt.datetime

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(
            resurfacingEnabled=row["resurfacing_enabled"],
            resurfacingCadence=row["resurfacing_cadence"],
            embeddingsEnabled=row["embeddings_enabled"],
            embeddingsAvailable=embeddings.ready,
            updatedAt=row["updated_at"],
        )


class ProcessingSummary(WireModel):
    """Whole-library counts by Memory status; one paginated Memory list cannot add these up."""

    queued: int
    processing: int
    ready: int
    failed: int
    total: int


class ExploreMonth(WireModel):
    month: dt.date
    memoryCount: int


class ResurfacingMemory(WireModel):
    """The Memory a resurfacing card points at: the same card every other projection answers with."""

    id: str
    kind: MemoryKind
    status: MemoryStatus
    sourceApp: str | None
    sourceUrl: str | None
    sourceDomain: str | None
    title: str | None
    capturedAt: dt.datetime
    previewUrl: str | None

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(
            id=str(row["id"]),
            kind=row["kind"],
            status=row["status"],
            sourceApp=row["source_app"],
            sourceUrl=row["source_url"],
            sourceDomain=row["source_domain"],
            title=row["title"],
            capturedAt=row["captured_at"],
            previewUrl=preview_url(row["id"], row["preview_key"]),
        )


class ResurfacingAnchor(WireModel):
    """The newer Memory that pulled the older one back up."""

    id: str
    title: str | None
    capturedAt: dt.datetime


class ResurfacingUpdate(WireModel):
    memory: ResurfacingMemory
    relatedTo: ResurfacingAnchor
    reason: str
    similarity: float

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(
            memory=ResurfacingMemory.from_row(row),
            relatedTo=ResurfacingAnchor(
                id=str(row["related_id"]),
                title=row["related_title"],
                capturedAt=row["related_captured_at"],
            ),
            # The client shows this text and never learns which pair produced it.
            reason="Related to a newer Memory in your Trove",
            similarity=float(row["similarity"]),
        )


class ResurfacingPage(WireModel):
    enabled: bool
    cadence: ResurfacingCadence
    updates: list[ResurfacingUpdate]


class Plan(WireModel):
    """The account's storage allowance: the plan the domain owns plus what this account has used."""

    id: str
    name: str
    storageLimitBytes: int
    storageUsedBytes: int
    storageRemainingBytes: int

    @classmethod
    def from_usage(cls, plan: StoragePlan, used_bytes: int) -> Self:
        return cls(
            id=plan.id,
            name=plan.name,
            storageLimitBytes=plan.limit_bytes,
            storageUsedBytes=used_bytes,
            storageRemainingBytes=max(0, plan.limit_bytes - used_bytes),
        )


@router.get("/me")
async def me(principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    return respond({"user": principal})


@router.get("/plan")
async def get_plan(subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    row = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}, usage AS (
             SELECT u.storage_plan, COALESCE(SUM(a.byte_size), 0)::bigint AS storage_used_bytes
             FROM app_users u
             LEFT JOIN assets a ON a.user_id=u.id AND a.status IN ('pending_upload','uploaded','attached')
             WHERE u.id=(SELECT user_id FROM auth)
               AND NOT (SELECT deleted FROM auth) AND NOT (SELECT deletion_pending FROM auth)
             GROUP BY u.storage_plan
           )
           SELECT (SELECT deleted FROM auth) AS deleted,
             (SELECT deletion_pending FROM auth) AS deletion_pending,
             (SELECT user_id FROM auth) AS user_id,
             usage.storage_plan, usage.storage_used_bytes
           FROM auth LEFT JOIN usage ON TRUE""",
        subject.subject,
        subject.email,
        subject.display_name,
    )
    if row is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(row)
    if row["storage_plan"] is None:
        raise ApiError(500, "account_not_found", "The account plan could not be loaded.")
    try:
        plan = Plan.from_usage(get_storage_plan(row["storage_plan"]), int(row["storage_used_bytes"]))
    except ValueError as error:
        raise ApiError(500, "invalid_storage_plan", "The account plan is not supported.") from error
    return respond({"plan": plan})


@router.get("/processing")
async def processing_summary(subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    rows = await fetch(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT a.deleted, a.deletion_pending, a.user_id, counts.status, counts.memory_count
            FROM auth a
            LEFT JOIN LATERAL (
              SELECT status, count(*)::int AS memory_count
              FROM memories WHERE user_id=a.user_id AND deleted_at IS NULL GROUP BY status
            ) counts ON NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL""",
        subject.subject,
        subject.email,
        subject.display_name,
    )
    if not rows:  # pragma: no cover - the auth anchor always yields at least one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(rows[0])
    counts: dict[MemoryStatus, int] = {
        row["status"]: int(row["memory_count"]) for row in rows if row["status"] is not None
    }
    return respond(
        {
            "processing": ProcessingSummary(
                queued=counts.get(MemoryStatus.QUEUED, 0),
                processing=counts.get(MemoryStatus.PROCESSING, 0),
                ready=counts.get(MemoryStatus.READY, 0),
                failed=counts.get(MemoryStatus.FAILED, 0),
                total=sum(counts.values()),
            )
        }
    )


@router.get("/preferences")
async def get_preferences(subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    row = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT a.deleted, a.deletion_pending, a.user_id,
              prefs.resurfacing_enabled, prefs.resurfacing_cadence,
              prefs.embeddings_enabled, prefs.updated_at
            FROM auth a
            LEFT JOIN user_preferences prefs
              ON prefs.user_id=a.user_id AND NOT a.deleted AND NOT a.deletion_pending""",
        subject.subject,
        subject.email,
        subject.display_name,
    )
    if row is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(row)
    preferences = (
        SavedPreferenceSettings.from_row(row) if row["updated_at"] is not None else PreferenceSettings.defaults()
    )
    return respond({"preferences": preferences})


@router.patch("/preferences")
async def patch_preferences(request: Request, subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    """Persist the choice only; the worker's embedding reconcile converges the library on it."""
    payload = await parse_body(UpdatePreferencesRequest, request, "invalid_preferences", "Invalid preferences.")

    row = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}, saved AS (
             INSERT INTO user_preferences(user_id,resurfacing_enabled,resurfacing_cadence,embeddings_enabled)
             SELECT (SELECT user_id FROM auth),
               CASE WHEN COALESCE($4,false) THEN COALESCE($5,false) ELSE false END,
               COALESCE($6,'weekly'),COALESCE($4,false)
             WHERE NOT (SELECT deleted FROM auth) AND NOT (SELECT deletion_pending FROM auth)
               AND (SELECT user_id FROM auth) IS NOT NULL
             ON CONFLICT(user_id) DO UPDATE SET
               resurfacing_enabled=CASE WHEN COALESCE($4,user_preferences.embeddings_enabled) THEN COALESCE($5,user_preferences.resurfacing_enabled) ELSE false END,
               resurfacing_cadence=COALESCE($6,user_preferences.resurfacing_cadence),
               embeddings_enabled=COALESCE($4,user_preferences.embeddings_enabled),updated_at=now()
             RETURNING resurfacing_enabled,resurfacing_cadence,embeddings_enabled,updated_at
           )
           SELECT (SELECT deleted FROM auth) AS deleted,
             (SELECT deletion_pending FROM auth) AS deletion_pending,
             (SELECT user_id FROM auth) AS user_id,
             saved.resurfacing_enabled, saved.resurfacing_cadence,
             saved.embeddings_enabled, saved.updated_at
           FROM auth LEFT JOIN saved ON TRUE""",
        subject.subject,
        subject.email,
        subject.display_name,
        payload.embeddingsEnabled,
        payload.resurfacingEnabled,
        payload.resurfacingCadence.value if payload.resurfacingCadence else None,
    )

    if row is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(row)
    if row["updated_at"] is None:  # pragma: no cover - the gates above write whenever auth passes
        raise ApiError(500, "internal_error", "The request could not be completed.")
    return respond({"preferences": SavedPreferenceSettings.from_row(row)})


@router.get("/explore")
async def explore(subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    months = await fetch(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT a.deleted, a.deletion_pending, a.user_id, buckets.month, buckets.memory_count
            FROM auth a
            LEFT JOIN LATERAL (
              SELECT date_trunc('month',captured_at)::date AS month, count(*)::int AS memory_count
              FROM memories WHERE user_id=a.user_id AND deleted_at IS NULL AND captured_at >= now()-interval '12 months'
              GROUP BY 1 ORDER BY 1 DESC LIMIT 12
            ) buckets ON NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL""",
        subject.subject,
        subject.email,
        subject.display_name,
    )
    if not months:  # pragma: no cover - the auth anchor always yields at least one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(months[0])
    return respond(
        {
            "months": [
                ExploreMonth(month=row["month"], memoryCount=row["memory_count"])
                for row in months
                if row["month"] is not None
            ],
        }
    )


@router.get("/updates")
async def updates(subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    settings = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}
            SELECT (SELECT deleted FROM auth) AS deleted,
              (SELECT deletion_pending FROM auth) AS deletion_pending,
              (SELECT user_id FROM auth) AS user_id,
              prefs.resurfacing_enabled, prefs.resurfacing_cadence, prefs.embeddings_enabled
            FROM auth LEFT JOIN user_preferences prefs ON prefs.user_id=auth.user_id""",
        subject.subject,
        subject.email,
        subject.display_name,
    )
    if settings is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    user_id = resolve_auth_state(settings)
    cadence = (
        settings["resurfacing_cadence"] if settings["resurfacing_enabled"] is not None else ResurfacingCadence.WEEKLY
    )
    if (
        settings["resurfacing_enabled"] is None
        or not settings["resurfacing_enabled"]
        or not settings["embeddings_enabled"]
        or cadence == ResurfacingCadence.OFF
    ):
        return respond(ResurfacingPage(enabled=False, cadence=cadence, updates=[]))

    model_set = embeddings.models()
    if model_set is None:
        return respond(ResurfacingPage(enabled=True, cadence=cadence, updates=[]))
    related = await find_resurfacing_memories(str(user_id), model_set.space_id)
    if not related:
        return respond(ResurfacingPage(enabled=True, cadence=cadence, updates=[]))

    rows = await fetch(
        f"""SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title, m.captured_at,
            recent.id AS related_id, recent.title AS related_title, recent.captured_at AS related_captured_at,
            matches.similarity,
            {PREVIEW_KEY_SUBQUERY}
           FROM unnest($2::uuid[],$3::uuid[],$4::float8[]) AS matches(memory_id,related_id,similarity)
           JOIN memories m ON m.id=matches.memory_id AND m.user_id=$1 AND m.deleted_at IS NULL
           JOIN memories recent ON recent.id=matches.related_id AND recent.user_id=$1 AND recent.deleted_at IS NULL
           ORDER BY matches.similarity DESC, m.captured_at DESC LIMIT {RESURFACING_PAGE_SIZE}""",
        user_id,
        [uuid.UUID(str(item["memoryId"])) for item in related],
        [uuid.UUID(str(item["relatedId"])) for item in related],
        [float(item["similarity"]) for item in related],
    )
    return respond(
        ResurfacingPage(
            enabled=True,
            cadence=cadence,
            updates=[ResurfacingUpdate.from_row(row) for row in rows],
        )
    )
