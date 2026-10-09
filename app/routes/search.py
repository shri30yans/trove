"""Hybrid lexical and embedding search, plus related memories."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from typing import Self

from fastapi import APIRouter, Depends, Request

from app.auth import Principal, as_uuid, require_auth
from app.db import current_request_id, execute, fetch, fetchrow
from app.domain.retrieval import (
    RELATED_CANDIDATE_LIMIT,
    RELATED_MIN_SIMILARITY,
    RELATED_PAGE_SIZE,
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_LIMIT,
    SEARCH_MIN_LIMIT,
    MatchType,
    RelationKind,
    candidate_limit_for,
    match_type,
    parse_limit,
    relation_for,
)
from app.embedding import Embedding, EmbeddingError, embeddings, vector_literal
from app.errors import ApiError, ApiJSONResponse, respond
from app.queries import PREVIEW_KEY_SUBQUERY
from app.schemas import RelatedFeedbackRequest, parse_body, parse_kind_param
from app.serialize import MemoryCard, Row, WireModel, preview_url
from app.times import parse_timestamp

router = APIRouter(dependencies=[Depends(require_auth)])
logger = logging.getLogger("trove.api")

_SEMANTIC_SEARCH_CTE = """eligible_memories AS (
     SELECT m.id FROM memories m
     WHERE m.user_id=$1 AND m.deleted_at IS NULL
       AND ($3::text IS NULL OR m.kind::text=$3)
       AND ($4::uuid IS NULL OR EXISTS (
         SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$4 AND ms.user_id=m.user_id
       ))
       AND ($5::text IS NULL OR m.source_domain=$5)
       AND ($6::timestamptz IS NULL OR m.captured_at >= $6::timestamptz)
       AND ($7::timestamptz IS NULL OR m.captured_at < $7::timestamptz)
   ), eligible_assets AS (
     SELECT DISTINCT ma.asset_id FROM memory_assets ma
     JOIN eligible_memories em ON em.id=ma.memory_id
     WHERE ma.user_id=$1
   ), vector_memory_hits AS (
     SELECT e.memory_id,e.asset_id,1-(e.embedding <=> $10::vector) AS similarity
     FROM embeddings e
     WHERE e.user_id=$1 AND e.embedding_space=$11
       AND (e.memory_id IN (SELECT id FROM eligible_memories)
         OR e.asset_id IN (SELECT asset_id FROM eligible_assets))
     ORDER BY e.embedding <=> $10::vector
     LIMIT $12
   ), semantic_hits AS (
     SELECT hits.memory_id,max(hits.similarity)::float AS semantic_score
     FROM (
       SELECT vh.memory_id,vh.similarity
       FROM vector_memory_hits vh WHERE vh.memory_id IS NOT NULL
       UNION ALL
       SELECT ma.memory_id,vh.similarity
       FROM vector_memory_hits vh
       JOIN memory_assets ma ON ma.asset_id=vh.asset_id AND ma.user_id=$1
       WHERE vh.asset_id IS NOT NULL
     ) hits
     GROUP BY hits.memory_id ORDER BY max(hits.similarity) DESC LIMIT $9
   )"""
_EMPTY_SEMANTIC_SEARCH_CTE = (
    "semantic_hits AS (SELECT NULL::uuid AS memory_id,NULL::float AS semantic_score WHERE false)"
)
_SEARCH_SQL_TEMPLATE = rf"""WITH q AS (SELECT websearch_to_tsquery('simple', $2) AS terms),
       __SEMANTIC_SEARCH_CTE__, ranked AS (
        SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
          m.description, m.user_note, m.page_text, m.captured_at,
          CASE WHEN m.search_document @@ q.terms THEN ts_rank_cd(m.search_document, q.terms) ELSE 0 END AS lexical_score,
          COALESCE(sh.semantic_score,0)::float AS semantic_score,
          m.search_document, m.content_text,
          {PREVIEW_KEY_SUBQUERY}
        FROM memories m CROSS JOIN q LEFT JOIN semantic_hits sh ON sh.memory_id=m.id
        WHERE m.user_id=$1 AND m.deleted_at IS NULL
          AND ($3::text IS NULL OR m.kind::text=$3)
          AND ($4::uuid IS NULL OR EXISTS (SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$4 AND ms.user_id=m.user_id))
          AND ($5::text IS NULL OR m.source_domain=$5)
          AND ($6::timestamptz IS NULL OR m.captured_at >= $6::timestamptz)
          AND ($7::timestamptz IS NULL OR m.captured_at < $7::timestamptz)
          AND ($8::text IS NULL OR EXISTS (SELECT 1 FROM memory_tags mt WHERE mt.memory_id=m.id AND mt.user_id=m.user_id AND mt.tag=$8))
          AND (m.search_document @@ q.terms OR sh.memory_id IS NOT NULL)
      ), scored AS (
        SELECT *,
          CASE WHEN lexical_score > 0 THEN row_number() OVER (ORDER BY lexical_score DESC, captured_at DESC) END AS lexical_rank,
          CASE WHEN semantic_score > 0 THEN row_number() OVER (ORDER BY semantic_score DESC, captured_at DESC) END AS semantic_rank
        FROM ranked
      ), limited AS (
        SELECT *, coalesce(1.0 / lexical_rank, 0) + coalesce(1.0 / semantic_rank, 0) AS score
        FROM scored ORDER BY score DESC, captured_at DESC LIMIT $9
      )
      SELECT limited.*,
        CASE WHEN limited.search_document @@ q.terms THEN
          ts_headline('simple', coalesce(content_text,page_text,title,''), q.terms,
            'MaxFragments=2,MinWords=5,MaxWords=24,FragmentDelimiter= … ')
          ELSE left(coalesce(description,title,user_note,content_text,''), 240) END AS match_excerpt
      FROM limited CROSS JOIN q ORDER BY score DESC, captured_at DESC"""


def _search_statement(use_semantic_search: bool) -> str:
    semantic_cte = _SEMANTIC_SEARCH_CTE if use_semantic_search else _EMPTY_SEMANTIC_SEARCH_CTE
    return _SEARCH_SQL_TEMPLATE.replace("__SEMANTIC_SEARCH_CTE__", semantic_cte)


_RELATED_SEARCH_SQL = f"""WITH source_state AS (
     SELECT EXISTS(SELECT 1 FROM memories WHERE id=$2 AND user_id=$1 AND deleted_at IS NULL) AS memory_exists,
       COALESCE((SELECT embeddings_enabled FROM user_preferences WHERE user_id=$1),false) AS embeddings_enabled
   ), source_vectors AS (
     SELECT e.embedding FROM source_state state JOIN embeddings e
       ON state.memory_exists AND state.embeddings_enabled
     WHERE e.user_id=$1 AND e.memory_id=$2 AND e.embedding_space=$3
     UNION ALL
     SELECT e.embedding FROM source_state state JOIN embeddings e
       ON state.memory_exists AND state.embeddings_enabled
     JOIN memory_assets ma ON ma.asset_id=e.asset_id AND ma.user_id=e.user_id
     WHERE e.user_id=$1 AND ma.memory_id=$2 AND e.embedding_space=$3 AND e.modality='image'
   ), vector_hits AS (
     SELECT target.memory_id,target.asset_id,target.similarity
     FROM source_vectors src
     CROSS JOIN LATERAL (
       SELECT e.memory_id,e.asset_id,1-(e.embedding <=> src.embedding) AS similarity
       FROM embeddings e
       WHERE e.user_id=$1 AND e.embedding_space=$3
         AND (
           (e.memory_id IS NOT NULL AND EXISTS (
             SELECT 1 FROM memories active_memory WHERE active_memory.id=e.memory_id
               AND active_memory.user_id=e.user_id AND active_memory.deleted_at IS NULL
           ))
           OR (e.asset_id IS NOT NULL AND EXISTS (
             SELECT 1 FROM memory_assets ma JOIN memories active_memory
               ON active_memory.id=ma.memory_id AND active_memory.user_id=ma.user_id
             WHERE ma.asset_id=e.asset_id AND ma.user_id=e.user_id AND active_memory.deleted_at IS NULL
           ))
         )
       ORDER BY e.embedding <=> src.embedding
       LIMIT $4
     ) target
   ), memory_hits AS (
     SELECT vh.memory_id,vh.similarity FROM vector_hits vh WHERE vh.memory_id IS NOT NULL
     UNION ALL
     SELECT ma.memory_id,vh.similarity FROM vector_hits vh
     JOIN memory_assets ma ON ma.asset_id=vh.asset_id AND ma.user_id=$1
     WHERE vh.asset_id IS NOT NULL
   ), related_candidates AS (
     SELECT m.id AS memory_id,max(hit.similarity)::float AS similarity
     FROM memory_hits hit JOIN memories m ON m.id=hit.memory_id AND m.user_id=$1
     WHERE m.id<>$2 AND m.deleted_at IS NULL
     GROUP BY m.id
   ), candidate_page AS (
     SELECT candidate.memory_id,candidate.similarity FROM related_candidates candidate
     ORDER BY candidate.similarity DESC LIMIT $4
   ), filtered_hits AS (
     SELECT candidate.memory_id,candidate.similarity FROM candidate_page candidate
     WHERE candidate.similarity >= $5::float
       AND NOT EXISTS (
         SELECT 1 FROM memory_relation_feedback f
         WHERE f.user_id=$1 AND f.memory_id=$2
           AND f.related_memory_id=candidate.memory_id AND f.is_related=false
       )
     ORDER BY candidate.similarity DESC LIMIT $6
   )
   SELECT state.memory_exists,state.embeddings_enabled,m.id,m.kind,m.status,m.source_app,m.source_url,
     m.source_domain,m.title,m.captured_at,hit.similarity,{PREVIEW_KEY_SUBQUERY}
   FROM source_state state
   LEFT JOIN filtered_hits hit ON state.memory_exists AND state.embeddings_enabled
   LEFT JOIN memories m ON m.id=hit.memory_id AND m.user_id=$1 AND m.deleted_at IS NULL
   ORDER BY hit.similarity DESC NULLS LAST"""


class SearchMemory(MemoryCard):
    """One ranked hit: the card, the text that matched, and how it was found."""

    description: str | None
    userNote: str | None
    pageText: str | None
    score: float
    matchType: MatchType
    matchExcerpt: str | None
    previewUrl: str | None

    @classmethod
    def from_row(cls, row: Row) -> Self:
        return cls(
            **MemoryCard.from_row(row).model_dump(),
            description=row["description"],
            userNote=row["user_note"],
            pageText=row["page_text"],
            score=float(row["score"]),
            matchType=match_type(float(row["lexical_score"] or 0), float(row["semantic_score"] or 0)),
            matchExcerpt=row["match_excerpt"],
            previewUrl=preview_url(row["id"], row["preview_key"]),
        )


class SearchResults(WireModel):
    query: str
    semanticSearch: bool
    memories: list[SearchMemory]


class RelatedMemory(MemoryCard):
    """One Memory beside this one, with the reason the two are shown together."""

    similarity: float
    relation: RelationKind
    reason: str
    previewUrl: str | None

    @classmethod
    def from_row(cls, row: Row) -> Self:
        similarity = float(row["similarity"])
        relation, reason = relation_for(similarity)
        return cls(
            **MemoryCard.from_row(row).model_dump(),
            similarity=similarity,
            relation=relation,
            reason=reason,
            previewUrl=preview_url(row["id"], row["preview_key"]),
        )


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


async def search_memories_for_user(principal: Principal, query: Mapping[str, str]) -> SearchResults:
    """Search one caller's memories using plain query values, shared by HTTP and MCP."""
    started = time.perf_counter()
    term = (query.get("q") or "").strip()
    tag = (query.get("tag") or "").strip().lower() or None
    if (not term and not tag) or len(term) > 1000:
        raise ApiError(400, "invalid_query", "Enter a search phrase up to 1,000 characters.")
    kind = parse_kind_param(query.get("kind"))
    limit = parse_limit(
        query.get("limit"), default=SEARCH_DEFAULT_LIMIT, minimum=SEARCH_MIN_LIMIT, maximum=SEARCH_MAX_LIMIT
    )
    after = parse_timestamp(query.get("after")) if query.get("after") else None
    before = parse_timestamp(query.get("before")) if query.get("before") else None
    user_id = uuid.UUID(principal.id)
    space_id = query.get("spaceId")
    if tag is not None and len(tag) > 40:
        raise ApiError(400, "invalid_tag", "Tags must be 40 characters or fewer.")
    mode = query.get("mode", "hybrid")
    if mode not in {"hybrid", "raw"}:
        raise ApiError(400, "invalid_search_mode", "Choose hybrid or raw text search.")

    embedding: Embedding | None = None
    if term and mode == "hybrid":
        embedding_started = time.perf_counter()
        embedding = await _embed_search_query(term, principal.embeddings_enabled)
        logger.info(
            "memory_search request_id=%s stage=embedding elapsed_ms=%.1f enabled=%s",
            current_request_id(),
            (time.perf_counter() - embedding_started) * 1000,
            embedding is not None,
        )

    args: list[object] = [
        user_id,
        term,
        kind,
        as_uuid(space_id) if space_id else None,
        query.get("source"),
        after,
        before,
        tag,
        limit,
    ]
    if embedding:
        args.extend((vector_literal(embedding), embedding.space_id, candidate_limit_for(limit)))

    lexical_started = time.perf_counter()
    rows = await fetch(_search_statement(embedding is not None), *args)
    logger.info(
        "memory_search request_id=%s stage=ranked_query elapsed_ms=%.1f results=%s",
        current_request_id(),
        (time.perf_counter() - lexical_started) * 1000,
        len(rows),
    )
    logger.info(
        "memory_search request_id=%s outcome=success elapsed_ms=%.1f mode=%s",
        current_request_id(),
        (time.perf_counter() - started) * 1000,
        mode,
    )
    return SearchResults(
        query=term, semanticSearch=embedding is not None, memories=[SearchMemory.from_row(row) for row in rows]
    )


@router.get("/memories/{memory_id}/related")
async def related_memories(memory_id: str, principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    started = time.perf_counter()
    user_id = uuid.UUID(principal.id)
    target = as_uuid(memory_id)
    model_set = embeddings.models()
    related_started = time.perf_counter()
    rows = await fetch(
        _RELATED_SEARCH_SQL,
        user_id,
        target,
        model_set.space_id if model_set else None,
        RELATED_CANDIDATE_LIMIT,
        RELATED_MIN_SIMILARITY,
        RELATED_PAGE_SIZE,
    )
    state = rows[0]
    if not state["memory_exists"]:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    if not state["embeddings_enabled"] or not model_set:
        outcome = "disabled" if not state["embeddings_enabled"] else "no_candidates"
        logger.info(
            "memory_related request_id=%s outcome=%s elapsed_ms=%.1f",
            current_request_id(),
            outcome,
            (time.perf_counter() - started) * 1000,
        )
        return respond({"memories": []})
    memories = [RelatedMemory.from_row(row) for row in rows if row["id"] is not None]
    logger.info(
        "memory_related request_id=%s stage=related_query elapsed_ms=%.1f results=%s",
        current_request_id(),
        (time.perf_counter() - related_started) * 1000,
        len(memories),
    )
    logger.info(
        "memory_related request_id=%s outcome=success elapsed_ms=%.1f",
        current_request_id(),
        (time.perf_counter() - started) * 1000,
    )
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
