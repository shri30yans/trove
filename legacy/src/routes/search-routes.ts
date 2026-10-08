import type { FastifyInstance, FastifyRequest } from 'fastify';
import { z } from 'zod';
import { pool } from '../db/pool.js';
import { aiAvailable, answerFromMemories } from '../ai.js';
import { embeddings } from '../embeddings.js';
import { findRelatedMemories, findSemanticMemories } from '../embedding-store.js';
import { askSchema, memoryKinds } from '../schemas.js';
import { createReadUrl } from '../storage.js';

async function aiEnabledForUser(userId: string) {
  const result = await pool.query<{ enabled: boolean }>(
    'SELECT COALESCE((SELECT ai_processing_enabled FROM user_preferences WHERE user_id=$1),false) AS enabled', [userId],
  );
  return result.rows[0]?.enabled === true;
}

async function embedSearchQuery(text: string, enabled: boolean, request: FastifyRequest) {
  if (!enabled) return null;
  try {
    return await embeddings.embed({ modality: 'text', text, purpose: 'query' });
  } catch (error) {
    request.log.warn(
      { errorType: error instanceof Error ? error.name : 'UnknownError' },
      'Local embedding failed; continuing with keyword retrieval.',
    );
    return null;
  }
}

export async function registerSearchRoutes(app: FastifyInstance) {
  app.get('/v1/search', async (request, reply) => {
    const query = request.query as { q?: string; limit?: string; kind?: string; spaceId?: string; source?: string; after?: string; before?: string };
    const q = query.q?.trim();
    if (!q || q.length > 1000) return reply.code(400).send({ error: { code: 'invalid_query', message: 'Enter a search phrase up to 1,000 characters.' } });
    if (query.kind && !memoryKinds.includes(query.kind as typeof memoryKinds[number])) {
      return reply.code(400).send({ error: { code: 'invalid_kind', message: 'Unknown Memory type.' } });
    }
    const limit = Math.min(50, Math.max(1, Number(query.limit) || 20));
    const after = query.after && !Number.isNaN(Date.parse(query.after)) ? new Date(query.after).toISOString() : null;
    const before = query.before && !Number.isNaN(Date.parse(query.before)) ? new Date(query.before).toISOString() : null;
    const userId = request.principal!.id;
    const enabled = await aiEnabledForUser(userId);
    const embedding = await embedSearchQuery(q, enabled, request);
    const semantic = embedding ? await findSemanticMemories(userId, embedding, limit, {
      kind: query.kind ?? null,
      spaceId: query.spaceId ?? null,
      sourceDomain: query.source ?? null,
      after,
      before,
    }) : [];

    const result = await pool.query(
      `WITH q AS (SELECT websearch_to_tsquery('simple', $2) AS terms),
       semantic_hits AS (
         SELECT * FROM unnest($3::uuid[],$4::float8[]) AS hit(memory_id,semantic_score)
       ), ranked AS (
        SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
          m.description, m.user_note, m.page_text, m.ai_summary, m.visual_description, m.captured_at,
          CASE WHEN m.search_document @@ q.terms THEN ts_rank_cd(m.search_document, q.terms) ELSE 0 END AS lexical_score,
          COALESCE(sh.semantic_score,0)::float AS semantic_score,
          CASE WHEN m.search_document @@ q.terms THEN
            ts_headline('simple', coalesce(m.content_text,m.page_text,m.ocr_text,m.transcript,m.ai_summary,m.title,''), q.terms,
              'MaxFragments=2,MinWords=5,MaxWords=24,FragmentDelimiter= … ')
            ELSE left(coalesce(m.ai_summary,m.visual_description,m.description,m.title,''), 240) END AS match_excerpt,
          (SELECT a.object_key FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id
            WHERE ma.memory_id=m.id AND ma.user_id=m.user_id ORDER BY ma.position LIMIT 1) AS preview_key
        FROM memories m CROSS JOIN q LEFT JOIN semantic_hits sh ON sh.memory_id=m.id
        WHERE m.user_id=$1 AND m.deleted_at IS NULL
          AND ($5::text IS NULL OR m.kind::text=$5)
          AND ($6::uuid IS NULL OR EXISTS (SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$6 AND ms.user_id=m.user_id))
          AND ($7::text IS NULL OR m.source_domain=$7)
          AND ($8::timestamptz IS NULL OR m.captured_at >= $8::timestamptz)
          AND ($9::timestamptz IS NULL OR m.captured_at <= $9::timestamptz)
          AND (m.search_document @@ q.terms OR sh.memory_id IS NOT NULL)
      )
      SELECT *, (0.42*lexical_score + 0.58*semantic_score) AS score
      FROM ranked ORDER BY score DESC, captured_at DESC LIMIT $10`,
      [userId, q, semantic.map((item) => item.memoryId), semantic.map((item) => item.similarity),
        query.kind ?? null, query.spaceId ?? null, query.source ?? null, after, before, limit],
    );
    const memories = await Promise.all(result.rows.map(async (row) => ({
      id: row.id, kind: row.kind, status: row.status, sourceApp: row.source_app, sourceUrl: row.source_url,
      sourceDomain: row.source_domain, title: row.title, description: row.description, userNote: row.user_note,
      pageText: row.page_text, summary: row.ai_summary, visualDescription: row.visual_description, capturedAt: row.captured_at,
      score: Number(row.score), matchType: Number(row.lexical_score) > 0 && Number(row.semantic_score) > 0 ? 'text_and_meaning' : Number(row.semantic_score) > 0 ? 'meaning' : 'text',
      matchExcerpt: row.match_excerpt,
      previewUrl: row.preview_key ? await createReadUrl(row.preview_key) : null,
    })));
    return { query: q, semanticSearch: embedding !== null, memories };
  });

  app.get('/v1/memories/:id/related', async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.principal!.id;
    const source = await pool.query<{ id: string }>(
      'SELECT id FROM memories WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL', [id, userId],
    );
    if (!source.rowCount) return reply.code(404).send({ error: { code: 'memory_not_found', message: 'Memory not found.' } });
    if (!await aiEnabledForUser(userId)) return { memories: [] };

    const modelSet = await embeddings.models();
    const similar = modelSet ? await findRelatedMemories(userId, id, modelSet.spaceId, 48) : [];
    let result;
    if (similar.length) {
      result = await pool.query(
        `WITH candidates AS (
           SELECT * FROM unnest($3::uuid[],$4::float8[]) AS hit(memory_id,similarity)
         )
         SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
           m.ai_summary, m.visual_description, m.captured_at,c.similarity,
           (SELECT a.object_key FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id
             WHERE ma.memory_id=m.id AND ma.user_id=m.user_id ORDER BY ma.position LIMIT 1) AS preview_key
         FROM candidates c JOIN memories m ON m.id=c.memory_id
         WHERE m.user_id=$1 AND m.deleted_at IS NULL AND c.similarity>=0.62
           AND NOT EXISTS (SELECT 1 FROM memory_relation_feedback f WHERE f.user_id=$1 AND f.memory_id=$2
             AND f.related_memory_id=m.id AND f.is_related=false)
         ORDER BY c.similarity DESC LIMIT 12`,
        [userId, id, similar.map((item) => item.memoryId), similar.map((item) => item.similarity)],
      );
    } else {
      result = await pool.query(
        `SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
          m.ai_summary, m.visual_description, m.captured_at,
          count(t.topic)::float/NULLIF((SELECT count(*) FROM memory_topics WHERE memory_id=$2 AND user_id=$1),0) AS similarity,
          (SELECT a.object_key FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id
            WHERE ma.memory_id=m.id AND ma.user_id=m.user_id ORDER BY ma.position LIMIT 1) AS preview_key
         FROM memories m JOIN memory_topics t ON t.memory_id=m.id AND t.user_id=m.user_id
         WHERE m.user_id=$1 AND m.id<>$2 AND m.deleted_at IS NULL
           AND t.topic IN (SELECT topic FROM memory_topics WHERE memory_id=$2 AND user_id=$1)
           AND NOT EXISTS (SELECT 1 FROM memory_relation_feedback f WHERE f.user_id=$1 AND f.memory_id=$2
             AND f.related_memory_id=m.id AND f.is_related=false)
         GROUP BY m.id ORDER BY similarity DESC, m.captured_at DESC LIMIT 12`,
        [userId, id],
      );
    }
    const memories = await Promise.all(result.rows.map(async (row) => ({
      id: row.id, kind: row.kind, status: row.status, sourceApp: row.source_app, sourceUrl: row.source_url,
      sourceDomain: row.source_domain, title: row.title, summary: row.ai_summary,
      visualDescription: row.visual_description, capturedAt: row.captured_at,
      similarity: Number(row.similarity ?? 0), relation: Number(row.similarity ?? 0) > 0.82 ? 'similar_idea' : 'same_topic',
      reason: Number(row.similarity ?? 0) > 0.82 ? 'Similar meaning or image' : 'Shared topic or visual content',
      previewUrl: row.preview_key ? await createReadUrl(row.preview_key) : null,
    })));
    return { memories };
  });

  app.put('/v1/memories/:id/related/:relatedId/feedback', async (request, reply) => {
    const parsed = z.object({ isRelated: z.boolean() }).safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_feedback', message: 'isRelated must be true or false.' } });
    const { id, relatedId } = request.params as { id: string; relatedId: string };
    const userId = request.principal!.id;
    const owned = await pool.query('SELECT count(*)::int AS count FROM memories WHERE user_id=$1 AND id=ANY($2::uuid[]) AND deleted_at IS NULL', [userId, [id, relatedId]]);
    if (owned.rows[0]!.count !== 2) return reply.code(404).send({ error: { code: 'memory_not_found', message: 'Memory not found.' } });
    await pool.query(
      `INSERT INTO memory_relation_feedback(user_id,memory_id,related_memory_id,is_related) VALUES($1,$2,$3,$4)
       ON CONFLICT(memory_id,related_memory_id) DO UPDATE SET is_related=EXCLUDED.is_related, created_at=now()`,
      [userId, id, relatedId, parsed.data.isRelated],
    );
    return { saved: true };
  });

  app.post('/v1/ask', async (request, reply) => {
    const parsed = askSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_question', message: parsed.error.issues[0]?.message ?? 'Invalid question.' } });
    if (!aiAvailable()) return reply.code(503).send({ error: { code: 'ask_unavailable', message: 'Ask requires an AI provider to be configured.' } });
    const userId = request.principal!.id;
    if (!await aiEnabledForUser(userId)) {
      return reply.code(403).send({ error: { code: 'ai_processing_disabled', message: 'Enable Memory understanding in preferences before using Ask.' } });
    }
    const { question, spaceId } = parsed.data;
    const embedding = await embedSearchQuery(question, true, request);
    const semantic = embedding ? await findSemanticMemories(userId, embedding, 64, { spaceId }) : [];
    const search = await pool.query(
      `WITH q AS (SELECT websearch_to_tsquery('simple',$2) AS terms),
       semantic_hits AS (
         SELECT * FROM unnest($3::uuid[],$4::float8[]) AS hit(memory_id,semantic_score)
       )
       SELECT m.id, m.title, m.source_url,
         left(concat_ws(E'\n',m.ai_summary,m.content_text,m.page_text,m.ocr_text,m.transcript,m.user_note,m.visual_description),3500) AS excerpt,
         (CASE WHEN m.search_document @@ q.terms THEN ts_rank_cd(m.search_document,q.terms) ELSE 0 END)*0.42+
         COALESCE(sh.semantic_score,0)*0.58 AS score
       FROM memories m CROSS JOIN q LEFT JOIN semantic_hits sh ON sh.memory_id=m.id
       WHERE m.user_id=$1 AND m.deleted_at IS NULL
         AND ($5::uuid IS NULL OR EXISTS(SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$5 AND ms.user_id=m.user_id))
         AND (m.search_document @@ q.terms OR sh.memory_id IS NOT NULL)
       ORDER BY score DESC LIMIT 8`,
      [userId, question, semantic.map((item) => item.memoryId), semantic.map((item) => item.similarity), spaceId ?? null],
    );
    const context = search.rows.filter((row) => Number(row.score) > 0).map((row) => ({
      id: row.id as string, title: row.title as string | null, sourceUrl: row.source_url as string | null,
      excerpt: (row.excerpt as string).slice(0, 3500),
    }));
    if (!context.length) return { answer: 'I couldn’t find a matching Memory in your Trove.', sources: [] };
    const answer = await answerFromMemories(question, context);
    const sourceIds = new Set(answer.sourceIds);
    const sources = context.filter((item) => sourceIds.has(item.id));
    return { answer: answer.answer, sources };
  });
}
