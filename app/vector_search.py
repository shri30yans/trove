"""Vector storage and pgvector similarity queries over the shared embedding space."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from app.db import transaction
from app.domain.retrieval import (
    HNSW_EF_SEARCH,
    HNSW_ITERATIVE_SCAN,
    RELATED_CANDIDATE_LIMIT,
    RESURFACING_MIN_SIMILARITY,
    RESURFACING_PAGE_SIZE,
    RESURFACING_PER_MEMORY,
    RESURFACING_POOL,
    RESURFACING_REOPEN_DAYS,
    RESURFACING_WINDOW_DAYS,
    candidate_limit_for,
)
from app.embedding import Embedding, vector_literal


def _uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _vector_param(embedding: Embedding) -> str:
    return vector_literal(embedding)


async def save_memory_embedding(
    connection: Any, user_id: uuid.UUID, memory_id: uuid.UUID, embedding: Embedding
) -> None:
    if embedding.modality != "text":
        raise RuntimeError("A memory row can only store a text embedding.")
    await connection.execute(
        """INSERT INTO embeddings(user_id,memory_id,modality,embedding_space,model_id,model_revision,embedding)
           VALUES($1,$2,'text',$3,$4,$5,$6::vector)
           ON CONFLICT (memory_id,embedding_space) WHERE memory_id IS NOT NULL DO UPDATE SET
             model_id=EXCLUDED.model_id, model_revision=EXCLUDED.model_revision,
             embedding=EXCLUDED.embedding, updated_at=now()""",
        user_id,
        memory_id,
        embedding.space_id,
        embedding.model_id,
        embedding.model_revision,
        _vector_param(embedding),
    )


async def save_asset_embedding(
    connection: Any, user_id: uuid.UUID, asset_id: uuid.UUID, checksum: str | None, embedding: Embedding
) -> None:
    if embedding.modality != "image":
        raise RuntimeError("An asset row can only store an image embedding.")
    await connection.execute(
        """INSERT INTO embeddings(user_id,asset_id,modality,embedding_space,model_id,model_revision,source_checksum_sha256,embedding)
           VALUES($1,$2,'image',$3,$4,$5,$6,$7::vector)
           ON CONFLICT (asset_id,embedding_space) WHERE asset_id IS NOT NULL DO UPDATE SET
             model_id=EXCLUDED.model_id, model_revision=EXCLUDED.model_revision,
             source_checksum_sha256=EXCLUDED.source_checksum_sha256,
             embedding=EXCLUDED.embedding, updated_at=now()""",
        user_id,
        asset_id,
        embedding.space_id,
        embedding.model_id,
        embedding.model_revision,
        checksum,
        _vector_param(embedding),
    )


async def _vector_query(sql: str, args: Sequence[Any]) -> list[dict[str, Any]]:
    async with transaction() as connection:
        # set_config(..., is_local => true) is SET LOCAL; it takes a bind parameter, SET does not.
        await connection.fetchval(
            "SELECT set_config('hnsw.ef_search', $1, true), set_config('hnsw.iterative_scan', $2, true)",
            str(HNSW_EF_SEARCH),
            HNSW_ITERATIVE_SCAN,
        )
        return [dict(row) for row in await connection.fetch(sql, *args)]


async def find_semantic_memories(
    user_id: str,
    embedding: Embedding,
    limit: int,
    kind: str | None = None,
    space_id: str | None = None,
    source_domain: str | None = None,
    after: Any = None,
    before: Any = None,
) -> list[dict[str, float | str]]:
    rows = await _vector_query(
        """WITH eligible_memories AS (
             SELECT m.id FROM memories m
             WHERE m.user_id=$1 AND m.deleted_at IS NULL
               AND ($4::text IS NULL OR m.kind::text=$4)
               AND ($5::uuid IS NULL OR EXISTS (
                 SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$5 AND ms.user_id=m.user_id
               ))
               AND ($6::text IS NULL OR m.source_domain=$6)
               AND ($7::timestamptz IS NULL OR m.captured_at >= $7::timestamptz)
               AND ($8::timestamptz IS NULL OR m.captured_at < $8::timestamptz)
           ), eligible_assets AS (
             SELECT DISTINCT ma.asset_id FROM memory_assets ma
             JOIN eligible_memories em ON em.id=ma.memory_id
             WHERE ma.user_id=$1
           ), vector_hits AS (
             SELECT e.memory_id,e.asset_id,1-(e.embedding <=> $3::vector) AS similarity
             FROM embeddings e
             WHERE e.user_id=$1 AND e.embedding_space=$2
               AND (e.memory_id IN (SELECT id FROM eligible_memories)
                 OR e.asset_id IN (SELECT asset_id FROM eligible_assets))
             ORDER BY e.embedding <=> $3::vector
             LIMIT $9
           ), memory_hits AS (
             SELECT vh.memory_id,vh.similarity FROM vector_hits vh WHERE vh.memory_id IS NOT NULL
             UNION ALL
             SELECT ma.memory_id,vh.similarity FROM vector_hits vh
             JOIN memory_assets ma ON ma.asset_id=vh.asset_id AND ma.user_id=$1
             WHERE vh.asset_id IS NOT NULL
           )
           SELECT memory_id,max(similarity)::float AS similarity FROM memory_hits
           GROUP BY memory_id ORDER BY similarity DESC LIMIT $10""",
        [
            _uuid(user_id),
            embedding.space_id,
            _vector_param(embedding),
            kind,
            _uuid(space_id) if space_id else None,
            source_domain,
            after,
            before,
            candidate_limit_for(limit),
            limit,
        ],
    )
    return [
        {"memoryId": str(row["memory_id"]), "similarity": float(row["similarity"])}
        for row in rows
        if row["memory_id"] is not None
    ]


async def find_related_memories(
    user_id: str, memory_id: str, space_id: str, limit: int = RELATED_CANDIDATE_LIMIT
) -> list[dict[str, float | str]]:
    rows = await _vector_query(
        """WITH source_vectors AS (
             SELECT e.embedding FROM embeddings e
             WHERE e.user_id=$1 AND e.memory_id=$2 AND e.embedding_space=$3
             UNION ALL
             SELECT e.embedding FROM embeddings e
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
           )
           SELECT m.id AS memory_id,max(mh.similarity)::float AS similarity
           FROM memory_hits mh JOIN memories m ON m.id=mh.memory_id AND m.user_id=$1
           WHERE m.id<>$2 AND m.deleted_at IS NULL
           GROUP BY m.id ORDER BY similarity DESC LIMIT $5""",
        [_uuid(user_id), _uuid(memory_id), space_id, limit, limit],
    )
    return [{"memoryId": str(row["memory_id"]), "similarity": float(row["similarity"])} for row in rows]


async def find_resurfacing_memories(
    user_id: str,
    space_id: str,
    limit: int = RESURFACING_PAGE_SIZE,
    *,
    window: dt.timedelta = dt.timedelta(days=RESURFACING_WINDOW_DAYS),
    reopen: dt.timedelta = dt.timedelta(days=RESURFACING_REOPEN_DAYS),
    pool: int = RESURFACING_POOL,
    per_memory: int = RESURFACING_PER_MEMORY,
    min_similarity: float = RESURFACING_MIN_SIMILARITY,
) -> list[dict[str, float | str]]:
    rows = await _vector_query(
        """WITH eligible_older AS (
             SELECT m.id FROM memories m
             WHERE m.user_id=$1 AND m.deleted_at IS NULL AND m.created_at < now()-$4::interval
               AND (m.last_opened_at IS NULL OR m.last_opened_at < now()-$5::interval)
             ORDER BY m.captured_at DESC LIMIT $6
           ), eligible_recent AS (
             SELECT m.id FROM memories m
             WHERE m.user_id=$1 AND m.deleted_at IS NULL AND m.created_at > now()-$7::interval
           ), eligible_recent_assets AS (
             SELECT DISTINCT ma.asset_id FROM memory_assets ma
             JOIN eligible_recent r ON r.id=ma.memory_id WHERE ma.user_id=$1
           ), old_vectors AS (
             SELECT m.id AS memory_id,e.embedding FROM embeddings e
             JOIN memories m ON m.id=e.memory_id AND m.user_id=e.user_id
             JOIN eligible_older old ON old.id=m.id
             WHERE e.user_id=$1 AND e.embedding_space=$2
             UNION ALL
             SELECT ma.memory_id,e.embedding FROM embeddings e
             JOIN memory_assets ma ON ma.asset_id=e.asset_id AND ma.user_id=e.user_id
             JOIN eligible_older old ON old.id=ma.memory_id
             WHERE e.user_id=$1 AND e.embedding_space=$2 AND e.modality='image'
           ), vector_hits AS (
             SELECT old.memory_id AS old_memory_id,target.memory_id,target.asset_id,target.similarity
             FROM old_vectors old
             CROSS JOIN LATERAL (
               SELECT e.memory_id,e.asset_id,1-(e.embedding <=> old.embedding) AS similarity
               FROM embeddings e
               WHERE e.user_id=$1 AND e.embedding_space=$2
                 AND (e.memory_id IN (SELECT id FROM eligible_recent)
                   OR e.asset_id IN (SELECT asset_id FROM eligible_recent_assets))
               ORDER BY e.embedding <=> old.embedding LIMIT $8
             ) target
           ), memory_hits AS (
             SELECT vh.old_memory_id,vh.memory_id,vh.similarity FROM vector_hits vh WHERE vh.memory_id IS NOT NULL
             UNION ALL
             SELECT vh.old_memory_id,ma.memory_id,vh.similarity FROM vector_hits vh
             JOIN memory_assets ma ON ma.asset_id=vh.asset_id AND ma.user_id=$1
             WHERE vh.asset_id IS NOT NULL
           ), pairs AS (
             SELECT old_memory_id,memory_id,max(similarity)::float AS similarity FROM memory_hits
             WHERE memory_id<>old_memory_id GROUP BY old_memory_id,memory_id
           ), best_pairs AS (
             SELECT DISTINCT ON (old_memory_id) old_memory_id,memory_id,similarity
             FROM pairs WHERE similarity>=$9::float
             ORDER BY old_memory_id,similarity DESC
           )
           SELECT older.id AS memory_id,recent.id AS related_id,bp.similarity
           FROM best_pairs bp
           JOIN memories older ON older.id=bp.old_memory_id AND older.user_id=$1
           JOIN memories recent ON recent.id=bp.memory_id AND recent.user_id=$1
           ORDER BY bp.similarity DESC,older.captured_at DESC LIMIT $3""",
        [_uuid(user_id), space_id, limit, window, reopen, pool, window, per_memory, min_similarity],
    )
    return [
        {
            "memoryId": str(row["memory_id"]),
            "relatedId": str(row["related_id"]),
            "similarity": float(row["similarity"]),
        }
        for row in rows
    ]
