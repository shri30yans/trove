import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { pool } from '../db/pool.js';
import { createReadUrl } from '../storage.js';
import { aiAvailable } from '../ai.js';
import { enqueueMemoryProcessingBatch } from '../queue.js';
import { embeddings } from '../embeddings.js';
import { findResurfacingMemories } from '../embedding-store.js';

const preferencesSchema = z.object({
  resurfacingEnabled: z.boolean().optional(),
  resurfacingCadence: z.enum(['weekly', 'monthly', 'off']).optional(),
  aiProcessingEnabled: z.boolean().optional(),
}).refine((value) => Object.keys(value).length > 0);

export async function registerAccountRoutes(app: FastifyInstance) {
  app.get('/v1/me', async (request) => ({ user: request.principal }));

  app.get('/v1/preferences', async (request) => {
    const result = await pool.query(
      `SELECT resurfacing_enabled,resurfacing_cadence,ai_processing_enabled,updated_at
       FROM user_preferences WHERE user_id=$1`, [request.principal!.id],
    );
    const row = result.rows[0];
    return { preferences: { ...(row ? {
      resurfacingEnabled: row.resurfacing_enabled,
      resurfacingCadence: row.resurfacing_cadence,
      aiProcessingEnabled: row.ai_processing_enabled,
      updatedAt: row.updated_at,
      } : { resurfacingEnabled: false, resurfacingCadence: 'weekly', aiProcessingEnabled: false }),
      aiAvailable: aiAvailable(),
      embeddingsAvailable: await embeddings.isReady(),
    } };
  });

  app.patch('/v1/preferences', async (request, reply) => {
    const parsed = preferencesSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_preferences', message: parsed.error.issues[0]?.message ?? 'Invalid preferences.' } });
    const value = parsed.data;
    const modelSet = value.aiProcessingEnabled ? await embeddings.models() : null;
    if (value.aiProcessingEnabled && !modelSet) {
      return reply.code(503).send({ error: { code: 'embeddings_unavailable', message: 'The local text and image embedding service is not ready yet.' } });
    }
    const userId = request.principal!.id;
    const client = await pool.connect();
    let preference: {
      resurfacing_enabled: boolean;
      resurfacing_cadence: string;
      ai_processing_enabled: boolean;
      updated_at: Date;
    };
    try {
      await client.query('BEGIN');
      const result = await client.query<{
        resurfacing_enabled: boolean;
        resurfacing_cadence: string;
        ai_processing_enabled: boolean;
        updated_at: Date;
      }>(
        `INSERT INTO user_preferences(user_id,resurfacing_enabled,resurfacing_cadence,ai_processing_enabled)
         VALUES($1,CASE WHEN COALESCE($4,false) THEN COALESCE($2,false) ELSE false END,COALESCE($3,'weekly'),COALESCE($4,false))
         ON CONFLICT(user_id) DO UPDATE SET
           resurfacing_enabled=CASE WHEN COALESCE($4,user_preferences.ai_processing_enabled) THEN COALESCE($2,user_preferences.resurfacing_enabled) ELSE false END,
           resurfacing_cadence=COALESCE($3,user_preferences.resurfacing_cadence),
           ai_processing_enabled=COALESCE($4,user_preferences.ai_processing_enabled),updated_at=now()
         RETURNING resurfacing_enabled,resurfacing_cadence,ai_processing_enabled,updated_at`,
        [userId, value.resurfacingEnabled ?? null, value.resurfacingCadence ?? null, value.aiProcessingEnabled ?? null],
      );
      preference = result.rows[0]!;
      if (value.aiProcessingEnabled && modelSet) {
        const candidates = await client.query<{ id: string }>(
          `SELECT m.id
           FROM memories m
           WHERE m.user_id=$1 AND m.deleted_at IS NULL AND m.status IN ('ready','failed')
           AND (
             (COALESCE(m.title,'') || COALESCE(m.description,'') || COALESCE(m.user_note,'') ||
               COALESCE(m.content_text,'') || COALESCE(m.page_text,'') || COALESCE(m.ocr_text,'') ||
               COALESCE(m.transcript,'') || COALESCE(m.ai_summary,'') || COALESCE(m.visual_description,'')) <> ''
             AND NOT EXISTS (
               SELECT 1 FROM embeddings e WHERE e.memory_id=m.id AND e.embedding_space=$2
             )
             OR EXISTS (
               SELECT 1 FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id AND a.user_id=ma.user_id
               WHERE ma.memory_id=m.id AND ma.user_id=m.user_id AND a.mime_type LIKE 'image/%'
                 AND NOT EXISTS (
                   SELECT 1 FROM embeddings e WHERE e.asset_id=a.id AND e.embedding_space=$2
                 )
             )
           )
           ORDER BY m.created_at`, [userId, modelSet.spaceId],
        );
        const memoryIds = candidates.rows.map((row) => row.id);
        await enqueueMemoryProcessingBatch(client, userId, memoryIds);
        if (memoryIds.length) {
          await client.query(
            `UPDATE memories SET status='queued', processing_error=NULL, updated_at=now()
             WHERE user_id=$1 AND id=ANY($2::uuid[]) AND deleted_at IS NULL AND status IN ('ready','failed')`,
            [userId, memoryIds],
          );
        }
      }
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK').catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return { preferences: {
      resurfacingEnabled: preference.resurfacing_enabled,
      resurfacingCadence: preference.resurfacing_cadence,
      aiProcessingEnabled: preference.ai_processing_enabled,
      updatedAt: preference.updated_at,
      aiAvailable: aiAvailable(),
      embeddingsAvailable: await embeddings.isReady(),
    } };
  });

  app.get('/v1/explore', async (request) => {
    const userId = request.principal!.id;
    const [topics, months] = await Promise.all([
      pool.query(
        `SELECT t.topic, count(DISTINCT t.memory_id)::int AS memory_count,
          max(m.captured_at) AS latest_at
         FROM memory_topics t JOIN memories m ON m.id=t.memory_id AND m.user_id=t.user_id
         WHERE t.user_id=$1 AND m.deleted_at IS NULL AND m.captured_at >= now()-interval '1 year'
         GROUP BY t.topic HAVING count(DISTINCT t.memory_id) >= 2
         ORDER BY memory_count DESC, latest_at DESC LIMIT 8`, [userId],
      ),
      pool.query(
        `SELECT date_trunc('month',captured_at)::date AS month, count(*)::int AS memory_count
         FROM memories WHERE user_id=$1 AND deleted_at IS NULL AND captured_at >= now()-interval '12 months'
         GROUP BY 1 ORDER BY 1 DESC LIMIT 12`, [userId],
      ),
    ]);
    return {
      threads: topics.rows.map((row) => ({ topic: row.topic, memoryCount: row.memory_count, latestAt: row.latest_at })),
      months: months.rows.map((row) => ({ month: row.month, memoryCount: row.memory_count })),
    };
  });

  app.get('/v1/updates', async (request) => {
    const userId = request.principal!.id;
    const settings = await pool.query<{ resurfacing_enabled: boolean; resurfacing_cadence: string; ai_processing_enabled: boolean }>(
      'SELECT resurfacing_enabled,resurfacing_cadence,ai_processing_enabled FROM user_preferences WHERE user_id=$1', [userId],
    );
    if (!settings.rows[0]?.resurfacing_enabled || !settings.rows[0].ai_processing_enabled || settings.rows[0].resurfacing_cadence === 'off') {
      return { enabled: false, cadence: settings.rows[0]?.resurfacing_cadence ?? 'weekly', updates: [] };
    }
    const modelSet = await embeddings.models();
    if (!modelSet) return { enabled: true, cadence: settings.rows[0]!.resurfacing_cadence, updates: [] };
    const related = await findResurfacingMemories(userId, modelSet.spaceId);
    if (!related.length) return { enabled: true, cadence: settings.rows[0]!.resurfacing_cadence, updates: [] };
    const result = await pool.query(
      `SELECT older.id, older.kind, older.source_app, older.source_url, older.source_domain, older.title,
        older.ai_summary, older.visual_description, older.captured_at,
        recent.id AS related_id, recent.title AS related_title, recent.captured_at AS related_captured_at,
        matches.similarity,
        (SELECT a.object_key FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id
          WHERE ma.memory_id=older.id AND ma.user_id=older.user_id ORDER BY ma.position LIMIT 1) AS preview_key
       FROM unnest($2::uuid[],$3::uuid[],$4::float8[]) AS matches(memory_id,related_id,similarity)
       JOIN memories older ON older.id=matches.memory_id AND older.user_id=$1 AND older.deleted_at IS NULL
       JOIN memories recent ON recent.id=matches.related_id AND recent.user_id=$1 AND recent.deleted_at IS NULL
       ORDER BY matches.similarity DESC, older.captured_at DESC LIMIT 8`,
      [userId, related.map((item) => item.memoryId), related.map((item) => item.relatedId), related.map((item) => item.similarity)],
    );
    const updates = await Promise.all(result.rows.map(async (row) => ({
      memory: {
        id: row.id, kind: row.kind, sourceApp: row.source_app, sourceUrl: row.source_url,
        sourceDomain: row.source_domain, title: row.title, summary: row.ai_summary,
        visualDescription: row.visual_description, capturedAt: row.captured_at,
        previewUrl: row.preview_key ? await createReadUrl(row.preview_key) : null,
      },
      relatedTo: { id: row.related_id, title: row.related_title, capturedAt: row.related_captured_at },
      reason: 'Related to a newer Memory in your Trove',
      similarity: Number(row.similarity),
    })));
    return { enabled: true, cadence: settings.rows[0]!.resurfacing_cadence, updates };
  });
}
