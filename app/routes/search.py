"""Hybrid lexical and embedding search, plus related memories."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.auth import Principal, as_uuid, require_auth
from app.db import execute, fetch, fetchrow
from app.domain.retrieval import (
    RELATED_CANDIDATE_LIMIT,
    RELATED_MIN_SIMILARITY,
    RELATED_PAGE_SIZE,
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_LIMIT,
    SEARCH_MIN_LIMIT,
    match_type,
    parse_limit,
    relation_for,
)
from app.embedding import Embedding, EmbeddingError, embeddings
from app.errors import ApiError, ApiJSONResponse, respond
from app.queries import PREVIEW_KEY_SUBQUERY
from app.schemas import RelatedFeedbackRequest, parse_body, parse_kind_param
from app.serialize import memory_card
from app.times import parse_timestamp
from app.vector_search import find_related_memories, find_semantic_memories

router = APIRouter(dependencies=[Depends(require_auth)])
logger = logging.getLogger("trove.api")
_MEMORY_SPACES = """COALESCE((SELECT json_agg(json_build_object('id',s.id,'name',s.name,'color',s.color,'icon',s.icon)
    ORDER BY s.name) FROM memory_spaces ms JOIN spaces s ON s.id=ms.space_id AND s.deleted_at IS NULL
    WHERE ms.memory_id=m.id AND ms.user_id=m.user_id), '[]'::json) AS spaces"""


async def _embeddings_enabled_for_user(user_id: uuid.UUID) -> bool:
    row = await fetchrow(
        "SELECT COALESCE((SELECT embeddings_enabled FROM user_preferences WHERE user_id=$1),false) AS embeddings_enabled",
        user_id,
    )
    return bool(row and row["embeddings_enabled"])


async def _embed_search_query(text: str, enabled: bool, purpose: str = "query") -> Embedding | None:
    if not enabled:
        return None
    try:
        return await embeddings.embed_text(text, purpose=purpose)
    except EmbeddingError as error:
        raise ApiError(503, "embeddings_unavailable", "Embedding search is unavailable. Try again.") from error


@router.get("/search")
async def search(request: Request, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    return respond(await search_memories_for_user(principal, request.query_params))


async def search_memories_for_user(principal: Principal, query: Mapping[str, str]) -> dict[str, Any]:
    """Search one caller's memories using plain query values, shared by HTTP and MCP."""
    term = (query.get("q") or "").strip()
    if not term or len(term) > 1000:
        raise ApiError(400, "invalid_query", "Enter a search phrase up to 1,000 characters.")
    kind = parse_kind_param(query.get("kind"))
    limit = parse_limit(
        query.get("limit"), default=SEARCH_DEFAULT_LIMIT, minimum=SEARCH_MIN_LIMIT, maximum=SEARCH_MAX_LIMIT
    )
    after = parse_timestamp(query.get("after")) if query.get("after") else None
    before = parse_timestamp(query.get("before")) if query.get("before") else None
    user_id = uuid.UUID(principal.id)
    space_id = query.get("spaceId")

    embedding = await _embed_search_query(term, await _embeddings_enabled_for_user(user_id))
    semantic = (
        await find_semantic_memories(
            principal.id,
            embedding,
            limit,
            kind=kind,
            space_id=space_id,
            source_domain=query.get("source"),
            after=after,
            before=before,
        )
        if embedding
        else []
    )

    rows = await fetch(
        rf"""WITH q AS (SELECT websearch_to_tsquery('simple', $2) AS terms),
       semantic_hits AS (
         SELECT * FROM unnest($3::uuid[],$4::float8[]) AS hit(memory_id,semantic_score)
       ), ranked AS (
        SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
          m.description, m.user_note, m.page_text, m.captured_at,
          CASE WHEN m.search_document @@ q.terms THEN ts_rank_cd(m.search_document, q.terms) ELSE 0 END AS lexical_score,
          COALESCE(sh.semantic_score,0)::float AS semantic_score,
          m.search_document, m.content_text,
          {PREVIEW_KEY_SUBQUERY}
        FROM memories m CROSS JOIN q LEFT JOIN semantic_hits sh ON sh.memory_id=m.id
        WHERE m.user_id=$1 AND m.deleted_at IS NULL
          AND ($5::text IS NULL OR m.kind::text=$5)
          AND ($6::uuid IS NULL OR EXISTS (SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$6 AND ms.user_id=m.user_id))
          AND ($7::text IS NULL OR m.source_domain=$7)
          AND ($8::timestamptz IS NULL OR m.captured_at >= $8::timestamptz)
          AND ($9::timestamptz IS NULL OR m.captured_at < $9::timestamptz)
          AND (m.search_document @@ q.terms OR sh.memory_id IS NOT NULL)
      ), scored AS (
        SELECT *,
          CASE WHEN lexical_score > 0 THEN row_number() OVER (ORDER BY lexical_score DESC, captured_at DESC) END AS lexical_rank,
          CASE WHEN semantic_score > 0 THEN row_number() OVER (ORDER BY semantic_score DESC, captured_at DESC) END AS semantic_rank
        FROM ranked
      ), limited AS (
        SELECT *, coalesce(1.0 / lexical_rank, 0) + coalesce(1.0 / semantic_rank, 0) AS score
        FROM scored ORDER BY score DESC, captured_at DESC LIMIT $10
      )
      SELECT limited.*,
        CASE WHEN limited.search_document @@ q.terms THEN
          ts_headline('simple', coalesce(content_text,page_text,title,''), q.terms,
            'MaxFragments=2,MinWords=5,MaxWords=24,FragmentDelimiter= … ')
          ELSE left(coalesce(description,title,user_note,content_text,''), 240) END AS match_excerpt
      FROM limited CROSS JOIN q ORDER BY score DESC, captured_at DESC""",
        user_id,
        term,
        [uuid.UUID(str(item["memoryId"])) for item in semantic],
        [float(item["similarity"]) for item in semantic],
        kind,
        as_uuid(space_id) if space_id else None,
        query.get("source"),
        after,
        before,
        limit,
    )
    memories = [
        {
            **memory_card(row),
            "description": row["description"],
            "userNote": row["user_note"],
            "pageText": row["page_text"],
            "score": float(row["score"]),
            "matchType": match_type(float(row["lexical_score"] or 0), float(row["semantic_score"] or 0)),
            "matchExcerpt": row["match_excerpt"],
            "previewUrl": f"/v1/memories/{row['id']}/preview" if row["preview_key"] else None,
        }
        for row in rows
    ]
    return {"query": term, "semanticSearch": embedding is not None, "memories": memories}


@router.get("/memories/{memory_id}/related")
async def related_memories(memory_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    started = time.perf_counter()
    user_id = uuid.UUID(principal.id)
    target = as_uuid(memory_id)
    eligibility_started = time.perf_counter()
    source = await fetchrow(
        """SELECT
             EXISTS(SELECT 1 FROM memories WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL) AS memory_exists,
             COALESCE((SELECT embeddings_enabled FROM user_preferences WHERE user_id=$2),false) AS embeddings_enabled""",
        target,
        user_id,
    )
    logger.info("memory_related stage=eligibility elapsed_ms=%.1f", (time.perf_counter() - eligibility_started) * 1000)
    if source is None or not source["memory_exists"]:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    if not source["embeddings_enabled"]:
        logger.info("memory_related outcome=disabled elapsed_ms=%.1f", (time.perf_counter() - started) * 1000)
        return respond({"memories": []})

    model_set = embeddings.models()
    vector_started = time.perf_counter()
    similar = (
        await find_related_memories(principal.id, memory_id, model_set.space_id, RELATED_CANDIDATE_LIMIT)
        if model_set
        else []
    )
    logger.info(
        "memory_related stage=vector_search elapsed_ms=%.1f candidates=%s",
        (time.perf_counter() - vector_started) * 1000,
        len(similar),
    )
    hydrate_started = time.perf_counter()
    if similar:
        rows = await fetch(
            f"""WITH candidates AS (
                 SELECT * FROM unnest($3::uuid[],$4::float8[]) AS hit(memory_id,similarity)
               )
               SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
                 m.captured_at,c.similarity,
                 {_MEMORY_SPACES},
                 {PREVIEW_KEY_SUBQUERY}
               FROM candidates c JOIN memories m ON m.id=c.memory_id
               WHERE m.user_id=$1 AND m.deleted_at IS NULL AND c.similarity>=$5::float
                 AND NOT EXISTS (SELECT 1 FROM memory_relation_feedback f WHERE f.user_id=$1 AND f.memory_id=$2
                   AND f.related_memory_id=m.id AND f.is_related=false)
               ORDER BY c.similarity DESC LIMIT $6""",
            user_id,
            target,
            [uuid.UUID(str(item["memoryId"])) for item in similar],
            [float(item["similarity"]) for item in similar],
            RELATED_MIN_SIMILARITY,
            RELATED_PAGE_SIZE,
        )
    else:
        rows = []
    memories = []
    for row in rows:
        similarity = float(row["similarity"] or 0)
        relation, reason = relation_for(similarity)
        memories.append(
            {
                **memory_card(row),
                "similarity": similarity,
                "relation": relation,
                "reason": reason,
                "previewUrl": f"/v1/memories/{row['id']}/preview" if row["preview_key"] else None,
            }
        )
    logger.info("memory_related stage=hydrate elapsed_ms=%.1f", (time.perf_counter() - hydrate_started) * 1000)
    logger.info("memory_related outcome=success elapsed_ms=%.1f", (time.perf_counter() - started) * 1000)
    return respond({"memories": memories})


@router.put("/memories/{memory_id}/related/{related_id}/feedback")
async def save_relation_feedback(
    request: Request, memory_id: str, related_id: str, principal: Principal = Depends(require_auth)
) -> ApiJSONResponse:
    payload = await parse_body(RelatedFeedbackRequest, request, "invalid_feedback", "isRelated must be true or false.")
    user_id = uuid.UUID(principal.id)
    owned = await fetchrow(
        "SELECT count(*)::int AS count FROM memories WHERE user_id=$1 AND id=ANY($2::uuid[]) AND deleted_at IS NULL",
        user_id,
        [as_uuid(memory_id), as_uuid(related_id)],
    )
    if not owned or owned["count"] != 2:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    await execute(
        """INSERT INTO memory_relation_feedback(user_id,memory_id,related_memory_id,is_related) VALUES($1,$2,$3,$4)
           ON CONFLICT(memory_id,related_memory_id) DO UPDATE SET is_related=EXCLUDED.is_related, created_at=now()""",
        user_id,
        as_uuid(memory_id),
        as_uuid(related_id),
        payload.isRelated,
    )
    return respond({"saved": True})
