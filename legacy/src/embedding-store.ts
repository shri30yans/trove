import type { PoolClient, QueryResult, QueryResultRow } from 'pg';
import { pool } from './db/pool.js';
import { vectorLiteral, type Embedding } from './embeddings.js';

export type SemanticSearchScope = {
  kind?: string | null;
  spaceId?: string | null;
  sourceDomain?: string | null;
  after?: string | null;
  before?: string | null;
};

export type MemorySimilarity = { memoryId: string; similarity: number };

async function vectorQuery<T extends QueryResultRow>(sql: string, parameters: unknown[]): Promise<QueryResult<T>> {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL hnsw.ef_search = 120');
    await client.query('SET LOCAL hnsw.iterative_scan = strict_order');
    const result = await client.query<T>(sql, parameters);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK').catch(() => undefined);
    throw error;
  } finally {
    client.release();
  }
}

export async function saveMemoryEmbedding(client: PoolClient, userId: string, memoryId: string, embedding: Embedding) {
  if (embedding.modality !== 'text') throw new Error('A memory row can only store a text embedding.');
  await client.query(
    `INSERT INTO embeddings(user_id,memory_id,modality,embedding_space,model_id,model_revision,embedding)
     VALUES($1,$2,'text',$3,$4,$5,$6::vector)
     ON CONFLICT (memory_id,embedding_space) WHERE memory_id IS NOT NULL DO UPDATE SET
       model_id=EXCLUDED.model_id, model_revision=EXCLUDED.model_revision,
       embedding=EXCLUDED.embedding, updated_at=now()`,
    [userId, memoryId, embedding.spaceId, embedding.modelId, embedding.modelRevision, vectorLiteral(embedding.vector)],
  );
}

export async function saveAssetEmbedding(
  client: PoolClient,
  userId: string,
  assetId: string,
  checksum: string | null,
  embedding: Embedding,
) {
  if (embedding.modality !== 'image') throw new Error('An asset row can only store an image embedding.');
  await client.query(
    `INSERT INTO embeddings(user_id,asset_id,modality,embedding_space,model_id,model_revision,source_checksum_sha256,embedding)
     VALUES($1,$2,'image',$3,$4,$5,$6,$7::vector)
     ON CONFLICT (asset_id,embedding_space) WHERE asset_id IS NOT NULL DO UPDATE SET
       model_id=EXCLUDED.model_id, model_revision=EXCLUDED.model_revision,
       source_checksum_sha256=EXCLUDED.source_checksum_sha256,
       embedding=EXCLUDED.embedding, updated_at=now()`,
    [userId, assetId, embedding.spaceId, embedding.modelId, embedding.modelRevision, checksum, vectorLiteral(embedding.vector)],
  );
}

export async function findSemanticMemories(
  userId: string,
  embedding: Embedding,
  limit: number,
  scope: SemanticSearchScope = {},
): Promise<MemorySimilarity[]> {
  const candidateLimit = Math.min(500, Math.max(80, limit * 8));
  const result = await vectorQuery<{ memory_id: string; similarity: number }>(
    `WITH eligible_memories AS (
       SELECT m.id FROM memories m
       WHERE m.user_id=$1 AND m.deleted_at IS NULL
         AND ($4::text IS NULL OR m.kind::text=$4)
         AND ($5::uuid IS NULL OR EXISTS (
           SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$5 AND ms.user_id=m.user_id
         ))
         AND ($6::text IS NULL OR m.source_domain=$6)
         AND ($7::timestamptz IS NULL OR m.captured_at >= $7::timestamptz)
         AND ($8::timestamptz IS NULL OR m.captured_at <= $8::timestamptz)
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
     GROUP BY memory_id ORDER BY similarity DESC LIMIT $10`,
    [userId, embedding.spaceId, vectorLiteral(embedding.vector), scope.kind ?? null, scope.spaceId ?? null,
      scope.sourceDomain ?? null, scope.after ?? null, scope.before ?? null, candidateLimit, limit],
  );
  return result.rows.map((row) => ({ memoryId: row.memory_id, similarity: Number(row.similarity) }));
}

export async function findRelatedMemories(
  userId: string,
  memoryId: string,
  spaceId: string,
  limit = 48,
): Promise<MemorySimilarity[]> {
  const result = await vectorQuery<{ memory_id: string; similarity: number }>(
    `WITH source_vectors AS (
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
     GROUP BY m.id ORDER BY similarity DESC LIMIT $5`,
    [userId, memoryId, spaceId, limit, limit],
  );
  return result.rows.map((row) => ({ memoryId: row.memory_id, similarity: Number(row.similarity) }));
}

export async function findResurfacingMemories(userId: string, spaceId: string, limit = 8) {
  const result = await vectorQuery<{
    memory_id: string;
    related_id: string;
    similarity: number;
  }>(
    `WITH eligible_older AS (
       SELECT m.id FROM memories m
       WHERE m.user_id=$1 AND m.deleted_at IS NULL AND m.created_at < now()-interval '30 days'
         AND (m.last_opened_at IS NULL OR m.last_opened_at < now()-interval '21 days')
       ORDER BY m.captured_at DESC LIMIT 500
     ), eligible_recent AS (
       SELECT m.id FROM memories m
       WHERE m.user_id=$1 AND m.deleted_at IS NULL AND m.created_at > now()-interval '30 days'
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
         ORDER BY e.embedding <=> old.embedding LIMIT 16
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
       FROM pairs WHERE similarity>=0.68
       ORDER BY old_memory_id,similarity DESC
     )
     SELECT older.id AS memory_id,recent.id AS related_id,bp.similarity
     FROM best_pairs bp
     JOIN memories older ON older.id=bp.old_memory_id AND older.user_id=$1
     JOIN memories recent ON recent.id=bp.memory_id AND recent.user_id=$1
     ORDER BY bp.similarity DESC,older.captured_at DESC LIMIT $3`,
    [userId, spaceId, limit],
  );
  return result.rows.map((row) => ({
    memoryId: row.memory_id,
    relatedId: row.related_id,
    similarity: Number(row.similarity),
  }));
}
