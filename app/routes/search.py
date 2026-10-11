"""Hybrid lexical and embedding search, plus related memories."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Self

from fastapi import APIRouter, Depends, Request

from app.auth import AUTH_SUBJECT_CTE, VerifiedSubject, as_uuid, require_subject, resolve_auth_state
from app.db import current_request_id, fetch, fetchrow
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

router = APIRouter()
logger = logging.getLogger("trove.api")

_SEMANTIC_SEARCH_CTE = """eligible_memories AS (
     SELECT m.id FROM memories m
     WHERE m.user_id=(SELECT user_id FROM auth) AND m.deleted_at IS NULL
       AND ($5::text IS NULL OR m.kind::text=$5)
       AND ($6::uuid IS NULL OR EXISTS (
         SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$6 AND ms.user_id=m.user_id
       ))
       AND ($7::text IS NULL OR m.source_domain=$7)
       AND ($8::timestamptz IS NULL OR m.captured_at >= $8::timestamptz)
       AND ($9::timestamptz IS NULL OR m.captured_at < $9::timestamptz)
   ), eligible_assets AS (
     SELECT DISTINCT ma.asset_id FROM memory_assets ma
     JOIN eligible_memories em ON em.id=ma.memory_id
     WHERE ma.user_id=(SELECT user_id FROM auth)
   ), vector_memory_hits AS (
     SELECT e.memory_id,e.asset_id,1-(e.embedding <=> $12::vector) AS similarity
     FROM embeddings e
     WHERE e.user_id=(SELECT user_id FROM auth) AND e.embedding_space=$13
       AND (e.memory_id IN (SELECT id FROM eligible_memories)
         OR e.asset_id IN (SELECT asset_id FROM eligible_assets))
     ORDER BY e.embedding <=> $12::vector
     LIMIT $14
   ), semantic_hits AS (
     SELECT hits.memory_id,max(hits.similarity)::float AS semantic_score
     FROM (
       SELECT vh.memory_id,vh.similarity
       FROM vector_memory_hits vh WHERE vh.memory_id IS NOT NULL
       UNION ALL
       SELECT ma.memory_id,vh.similarity
       FROM vector_memory_hits vh
       JOIN memory_assets ma ON ma.asset_id=vh.asset_id AND ma.user_id=(SELECT user_id FROM auth)
       WHERE vh.asset_id IS NOT NULL
     ) hits
     GROUP BY hits.memory_id ORDER BY max(hits.similarity) DESC LIMIT $11
   )"""
_EMPTY_SEMANTIC_SEARCH_CTE = (
    "semantic_hits AS (SELECT NULL::uuid AS memory_id,NULL::float AS semantic_score WHERE false)"
)
_SEARCH_SQL_TEMPLATE = rf"""WITH {AUTH_SUBJECT_CTE}, q AS (SELECT websearch_to_tsquery('simple', $4) AS terms),
       __SEMANTIC_SEARCH_CTE__, ranked AS (
        SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
          m.description, m.user_note, m.page_text, m.captured_at,
          CASE WHEN m.search_document @@ q.terms THEN ts_rank_cd(m.search_document, q.terms) ELSE 0 END AS lexical_score,
          COALESCE(sh.semantic_score,0)::float AS semantic_score,
          m.search_document, m.content_text,
          {PREVIEW_KEY_SUBQUERY}
        FROM memories m CROSS JOIN q LEFT JOIN semantic_hits sh ON sh.memory_id=m.id
        WHERE m.user_id=(SELECT user_id FROM auth) AND m.deleted_at IS NULL
          AND ($5::text IS NULL OR m.kind::text=$5)
          AND ($6::uuid IS NULL OR EXISTS (SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$6 AND ms.user_id=m.user_id))
          AND ($7::text IS NULL OR m.source_domain=$7)
          AND ($8::timestamptz IS NULL OR m.captured_at >= $8::timestamptz)
          AND ($9::timestamptz IS NULL OR m.captured_at < $9::timestamptz)
          AND ($10::text IS NULL OR EXISTS (SELECT 1 FROM memory_tags mt WHERE mt.memory_id=m.id AND mt.user_id=m.user_id AND mt.tag=$10))
          AND (m.search_document @@ q.terms OR sh.memory_id IS NOT NULL)
      ), scored AS (
        SELECT *,
          CASE WHEN lexical_score > 0 THEN row_number() OVER (ORDER BY lexical_score DESC, captured_at DESC) END AS lexical_rank,
          CASE WHEN semantic_score > 0 THEN row_number() OVER (ORDER BY semantic_score DESC, captured_at DESC) END AS semantic_rank
        FROM ranked
      ), limited AS (
        SELECT *, coalesce(1.0 / lexical_rank, 0) + coalesce(1.0 / semantic_rank, 0) AS score
        FROM scored ORDER BY score DESC, captured_at DESC LIMIT $11
      ), found AS (
      SELECT limited.*,
        CASE WHEN limited.search_document @@ q.terms THEN
          ts_headline('simple', coalesce(content_text,page_text,title,''), q.terms,
            'MaxFragments=2,MinWords=5,MaxWords=24,FragmentDelimiter= … ')
          ELSE left(coalesce(description,title,user_note,content_text,''), 240) END AS match_excerpt
      FROM limited CROSS JOIN q ORDER BY score DESC, captured_at DESC)
      SELECT a.deleted, a.deletion_pending, a.user_id, hit.*
      FROM auth a LEFT JOIN LATERAL (
        SELECT * FROM found ORDER BY score DESC, captured_at DESC
      ) hit ON NOT a.deleted AND NOT a.deletion_pending AND a.user_id IS NOT NULL"""


def _search_statement(use_semantic_search: bool) -> str:
    semantic_cte = _SEMANTIC_SEARCH_CTE if use_semantic_search else _EMPTY_SEMANTIC_SEARCH_CTE
    return _SEARCH_SQL_TEMPLATE.replace("__SEMANTIC_SEARCH_CTE__", semantic_cte)


# The hybrid-mode embedding gate: one round trip that resolves the account and reports whether
# semantic search is on for it. Raw mode skips this entirely and answers in a single query.
_EMBEDDING_FLAG_SQL = f"""WITH {AUTH_SUBJECT_CTE}
  SELECT (SELECT deleted FROM auth) AS deleted,
    (SELECT deletion_pending FROM auth) AS deletion_pending,
    (SELECT user_id FROM auth) AS user_id,
    COALESCE((SELECT embeddings_enabled FROM user_preferences
              WHERE user_id=(SELECT user_id FROM auth)), false) AS embeddings_enabled
  FROM auth"""


_RELATED_SEARCH_SQL = f"""WITH {AUTH_SUBJECT_CTE}, source_state AS (
     SELECT (SELECT deleted FROM auth) AS deleted, (SELECT deletion_pending FROM auth) AS deletion_pending,
       (SELECT user_id FROM auth) AS user_id,
       EXISTS(SELECT 1 FROM memories WHERE id=$4 AND user_id=(SELECT user_id FROM auth) AND deleted_at IS NULL) AS memory_exists,
       COALESCE((SELECT embeddings_enabled FROM user_preferences WHERE user_id=(SELECT user_id FROM auth)),false) AS embeddings_enabled
   ), source_vectors AS (
     SELECT e.embedding FROM source_state state JOIN embeddings e
       ON state.memory_exists AND state.embeddings_enabled AND NOT state.deleted AND NOT state.deletion_pending
     WHERE e.user_id=(SELECT user_id FROM auth) AND e.memory_id=$4 AND e.embedding_space=$5
     UNION ALL
     SELECT e.embedding FROM source_state state JOIN embeddings e
       ON state.memory_exists AND state.embeddings_enabled AND NOT state.deleted AND NOT state.deletion_pending
     JOIN memory_assets ma ON ma.asset_id=e.asset_id AND ma.user_id=e.user_id
     WHERE e.user_id=(SELECT user_id FROM auth) AND ma.memory_id=$4 AND e.embedding_space=$5 AND e.modality='image'
   ), vector_hits AS (
     SELECT target.memory_id,target.asset_id,target.similarity
     FROM source_vectors src
     CROSS JOIN LATERAL (
       SELECT e.memory_id,e.asset_id,1-(e.embedding <=> src.embedding) AS similarity
       FROM embeddings e
       WHERE e.user_id=(SELECT user_id FROM auth) AND e.embedding_space=$5
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
       LIMIT $6
     ) target
   ), memory_hits AS (
     SELECT vh.memory_id,vh.similarity FROM vector_hits vh WHERE vh.memory_id IS NOT NULL
     UNION ALL
     SELECT ma.memory_id,vh.similarity FROM vector_hits vh
     JOIN memory_assets ma ON ma.asset_id=vh.asset_id AND ma.user_id=(SELECT user_id FROM auth)
     WHERE vh.asset_id IS NOT NULL
   ), related_candidates AS (
     SELECT m.id AS memory_id,max(hit.similarity)::float AS similarity
     FROM memory_hits hit JOIN memories m ON m.id=hit.memory_id AND m.user_id=(SELECT user_id FROM auth)
     WHERE m.id<>$4 AND m.deleted_at IS NULL
     GROUP BY m.id
   ), candidate_page AS (
     SELECT candidate.memory_id,candidate.similarity FROM related_candidates candidate
     ORDER BY candidate.similarity DESC LIMIT $6
   ), filtered_hits AS (
     SELECT candidate.memory_id,candidate.similarity FROM candidate_page candidate
     WHERE candidate.similarity >= $7::float
       AND NOT EXISTS (
         SELECT 1 FROM memory_relation_feedback f
         WHERE f.user_id=(SELECT user_id FROM auth) AND f.memory_id=$4
           AND f.related_memory_id=candidate.memory_id AND f.is_related=false
       )
     ORDER BY candidate.similarity DESC LIMIT $8
   )
   SELECT state.deleted,state.deletion_pending,state.user_id,state.memory_exists,state.embeddings_enabled,m.id,m.kind,m.status,m.source_app,m.source_url,
     m.source_domain,m.title,m.captured_at,hit.similarity,{PREVIEW_KEY_SUBQUERY}
   FROM source_state state
   LEFT JOIN filtered_hits hit ON state.memory_exists AND state.embeddings_enabled
     AND NOT state.deleted AND NOT state.deletion_pending
   LEFT JOIN memories m ON m.id=hit.memory_id AND m.user_id=state.user_id AND m.deleted_at IS NULL
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
async def search(request: Request, subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    return respond(await search_memories_for_user(subject, request.query_params))


async def search_memories_for_user(subject: VerifiedSubject, query: Mapping[str, str]) -> SearchResults:
    """Search one caller's memories using plain query values, shared by HTTP and MCP.

    Raw mode answers in a single round trip: the account resolution shares the ranked
    query. Hybrid mode first resolves the account and its embedding switch in one round
    trip, then embeds outside the database only when the switch is on.
    """
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
    space_id = query.get("spaceId")
    if tag is not None and len(tag) > 40:
        raise ApiError(400, "invalid_tag", "Tags must be 40 characters or fewer.")
    mode = query.get("mode", "hybrid")
    if mode not in {"hybrid", "raw"}:
        raise ApiError(400, "invalid_search_mode", "Choose hybrid or raw text search.")

    embeddings_enabled = False
    if term and mode == "hybrid":
        flag = await fetchrow(
            _EMBEDDING_FLAG_SQL,
            subject.subject,
            subject.email,
            subject.display_name,
        )
        if flag is None:  # pragma: no cover - the auth anchor always yields exactly one row
            raise ApiError(500, "internal_error", "The request could not be completed.")
        resolve_auth_state(flag)
        embeddings_enabled = bool(flag["embeddings_enabled"])

    embedding: Embedding | None = None
    if term and mode == "hybrid":
        embedding_started = time.perf_counter()
        embedding = await _embed_search_query(term, embeddings_enabled)
        logger.info(
            "memory_search request_id=%s stage=embedding elapsed_ms=%.1f enabled=%s",
            current_request_id(),
            (time.perf_counter() - embedding_started) * 1000,
            embedding is not None,
        )

    args: list[object] = [
        subject.subject,
        subject.email,
        subject.display_name,
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
    if not rows:  # pragma: no cover - the auth anchor always yields at least one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(rows[0])
    results = [SearchMemory.from_row(row) for row in rows if row["id"] is not None]
    logger.info(
        "memory_search request_id=%s stage=ranked_query elapsed_ms=%.1f results=%s",
        current_request_id(),
        (time.perf_counter() - lexical_started) * 1000,
        len(results),
    )
    logger.info(
        "memory_search request_id=%s outcome=success elapsed_ms=%.1f mode=%s",
        current_request_id(),
        (time.perf_counter() - started) * 1000,
        mode,
    )
    return SearchResults(query=term, semanticSearch=embedding is not None, memories=results)


@router.get("/memories/{memory_id}/related")
async def related_memories(memory_id: str, subject: VerifiedSubject = Depends(require_subject)) -> ApiJSONResponse:
    started = time.perf_counter()
    target = as_uuid(memory_id)
    model_set = embeddings.models()
    related_started = time.perf_counter()
    rows = await fetch(
        _RELATED_SEARCH_SQL,
        subject.subject,
        subject.email,
        subject.display_name,
        target,
        model_set.space_id if model_set else None,
        RELATED_CANDIDATE_LIMIT,
        RELATED_MIN_SIMILARITY,
        RELATED_PAGE_SIZE,
    )
    if not rows:  # pragma: no cover - the auth anchor always yields at least one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    state = rows[0]
    resolve_auth_state(state)
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
    request: Request, memory_id: str, related_id: str, subject: VerifiedSubject = Depends(require_subject)
) -> ApiJSONResponse:
    payload = await parse_body(RelatedFeedbackRequest, request, "invalid_feedback", "isRelated must be true or false.")
    saved = await fetchrow(
        f"""WITH {AUTH_SUBJECT_CTE}, owned AS (
             SELECT count(*)::int AS pair_count FROM memories
             WHERE user_id=(SELECT user_id FROM auth) AND id=ANY($4::uuid[]) AND deleted_at IS NULL
               AND NOT (SELECT deleted FROM auth) AND NOT (SELECT deletion_pending FROM auth)
           ), stored AS (
             INSERT INTO memory_relation_feedback(user_id,memory_id,related_memory_id,is_related)
             SELECT (SELECT user_id FROM auth),$5,$6,$7 FROM owned
             WHERE owned.pair_count=2
               AND NOT (SELECT deleted FROM auth) AND NOT (SELECT deletion_pending FROM auth)
             ON CONFLICT(memory_id,related_memory_id) DO UPDATE SET is_related=EXCLUDED.is_related, created_at=now()
             RETURNING related_memory_id
           )
           SELECT (SELECT deleted FROM auth) AS deleted,
             (SELECT deletion_pending FROM auth) AS deletion_pending,
             (SELECT user_id FROM auth) AS user_id,
             (SELECT pair_count FROM owned) AS pair_count
           FROM auth""",
        subject.subject,
        subject.email,
        subject.display_name,
        [as_uuid(memory_id), as_uuid(related_id)],
        as_uuid(memory_id),
        as_uuid(related_id),
        payload.isRelated,
    )
    if saved is None:  # pragma: no cover - the auth anchor always yields exactly one row
        raise ApiError(500, "internal_error", "The request could not be completed.")
    resolve_auth_state(saved)
    if saved["pair_count"] != 2:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    return respond({"saved": True})
