import type { FastifyInstance } from 'fastify';
import { enqueueMemoryProcessing } from '../queue.js';
import { pool } from '../db/pool.js';
import { config } from '../config.js';
import { createReadUrl, createUploadUrl, headObject, newObjectKey } from '../storage.js';
import { createMemorySchema, createUploadSchema, memoryKinds, sourceDomain, updateMemorySchema } from '../schemas.js';

function unique(values: string[]) { return [...new Set(values)]; }

async function validateOwnedIds(userId: string, ids: string[], table: 'spaces' | 'assets') {
  const values = unique(ids);
  if (!values.length) return true;
  const result = await pool.query<{ id: string; status?: string }>(
    table === 'spaces'
      ? 'SELECT id FROM spaces WHERE user_id = $1 AND id = ANY($2::uuid[]) AND deleted_at IS NULL'
      : "SELECT id, status FROM assets WHERE user_id = $1 AND id = ANY($2::uuid[]) AND status = 'uploaded'",
    [userId, values],
  );
  return result.rowCount === values.length;
}

function encodeCursor(capturedAt: Date, id: string) {
  return Buffer.from(`${capturedAt.toISOString()}|${id}`).toString('base64url');
}

function decodeCursor(value?: string) {
  if (!value) return null;
  try {
    const decoded = Buffer.from(value, 'base64url').toString('utf8');
    const separator = decoded.lastIndexOf('|');
    const capturedAt = new Date(decoded.slice(0, separator));
    const id = decoded.slice(separator + 1);
    if (separator < 0 || Number.isNaN(capturedAt.getTime()) || !/^[0-9a-f-]{36}$/i.test(id)) return null;
    return { capturedAt, id };
  } catch { return null; }
}

async function getMemory(userId: string, memoryId: string) {
  const result = await pool.query(
    `SELECT m.id, m.kind, m.status, m.processing_error, m.source_app, m.source_url, m.source_domain,
      m.title, m.description, m.user_note, m.content_text, m.page_text, m.ocr_text, m.transcript, m.ai_summary,
      m.visual_description, m.capture_metadata, m.captured_at, m.occurred_at, m.created_at, m.updated_at,
      COALESCE((SELECT json_agg(json_build_object('id',s.id,'name',s.name,'color',s.color,'icon',s.icon) ORDER BY s.name)
        FROM memory_spaces ms JOIN spaces s ON s.id=ms.space_id AND s.deleted_at IS NULL
        WHERE ms.memory_id=m.id AND ms.user_id=m.user_id), '[]'::json) AS spaces,
      COALESCE((SELECT json_agg(json_build_object('name',t.topic,'confidence',t.confidence) ORDER BY t.topic)
        FROM memory_topics t WHERE t.memory_id=m.id AND t.user_id=m.user_id), '[]'::json) AS topics,
      COALESCE((SELECT json_agg(json_build_object('id',e.id,'kind',e.entity_kind,'value',e.display_value,
          'normalizedValue',e.normalized_value,'confidence',e.confidence,'properties',e.properties,
          'confirmed',e.user_confirmed) ORDER BY e.confidence DESC)
        FROM memory_entities e WHERE e.memory_id=m.id AND e.user_id=m.user_id), '[]'::json) AS entities
     FROM memories m WHERE m.id=$1 AND m.user_id=$2 AND m.deleted_at IS NULL`,
    [memoryId, userId],
  );
  if (!result.rowCount) return null;
  const memory = result.rows[0]!;
  const assets = await pool.query(
    `SELECT a.id, a.original_filename, a.mime_type, a.byte_size, a.status, a.created_at, a.object_key, ma.role
     FROM assets a JOIN memory_assets ma ON ma.asset_id=a.id
     WHERE ma.memory_id=$1 AND ma.user_id=$2 ORDER BY ma.position`,
    [memoryId, userId],
  );
  return {
    id: memory.id, kind: memory.kind, status: memory.status, processingError: memory.processing_error,
    sourceApp: memory.source_app, sourceUrl: memory.source_url, sourceDomain: memory.source_domain,
    title: memory.title, description: memory.description, userNote: memory.user_note,
    contentText: memory.content_text, pageText: memory.page_text, ocrText: memory.ocr_text, transcript: memory.transcript,
    summary: memory.ai_summary, visualDescription: memory.visual_description, captureMetadata: memory.capture_metadata,
    capturedAt: memory.captured_at, occurredAt: memory.occurred_at, createdAt: memory.created_at, updatedAt: memory.updated_at,
    spaces: memory.spaces, topics: memory.topics, entities: memory.entities,
    assets: await Promise.all(assets.rows.map(async (asset) => ({
      id: asset.id, filename: asset.original_filename, mimeType: asset.mime_type, byteSize: Number(asset.byte_size),
      status: asset.status, role: asset.role, createdAt: asset.created_at, url: await createReadUrl(asset.object_key),
    }))),
  };
}

export async function registerMemoryRoutes(app: FastifyInstance) {
  app.post('/v1/uploads', async (request, reply) => {
    const parsed = createUploadSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_upload', message: parsed.error.issues[0]?.message ?? 'Invalid upload.' } });
    const { filename, mimeType, byteSize, checksumSha256 } = parsed.data;
    if (byteSize > config.MAX_UPLOAD_BYTES) return reply.code(413).send({ error: { code: 'upload_too_large', message: 'This file is larger than the configured upload limit.' } });
    if (!/^[\w.+-]+\/[\w.+-]+$/.test(mimeType)) return reply.code(400).send({ error: { code: 'invalid_mime_type', message: 'A valid MIME type is required.' } });
    const userId = request.principal!.id;
    const objectKey = newObjectKey(userId, filename);
    const created = await pool.query(
      `INSERT INTO assets(user_id, object_key, original_filename, mime_type, byte_size, checksum_sha256)
       VALUES($1,$2,$3,$4,$5,$6) RETURNING id`,
      [userId, objectKey, filename, mimeType, byteSize, checksumSha256 ?? null],
    );
    const assetId = created.rows[0]!.id as string;
    try {
      const uploadUrl = await createUploadUrl(objectKey, mimeType);
      return reply.code(201).send({
        assetId, uploadUrl, method: 'PUT', headers: { 'Content-Type': mimeType },
        expiresInSeconds: config.UPLOAD_URL_TTL_SECONDS,
      });
    } catch (error) {
      await pool.query("UPDATE assets SET status='failed' WHERE id=$1 AND user_id=$2", [assetId, userId]);
      throw error;
    }
  });

  app.post('/v1/uploads/:id/complete', async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.principal!.id;
    const result = await pool.query<{ object_key: string; byte_size: string; status: string }>(
      'SELECT object_key, byte_size, status FROM assets WHERE id=$1 AND user_id=$2', [id, userId],
    );
    const asset = result.rows[0];
    if (!asset) return reply.code(404).send({ error: { code: 'upload_not_found', message: 'Upload not found.' } });
    if (asset.status === 'uploaded' || asset.status === 'attached') return { assetId: id, status: asset.status };
    const stored = await headObject(asset.object_key);
    const actualSize = Number(stored.ContentLength ?? 0);
    if (!actualSize || actualSize !== Number(asset.byte_size) || actualSize > config.MAX_UPLOAD_BYTES) {
      return reply.code(422).send({ error: { code: 'upload_size_mismatch', message: 'The uploaded file size did not match the declared size.' } });
    }
    await pool.query("UPDATE assets SET status='uploaded', uploaded_at=now() WHERE id=$1 AND user_id=$2", [id, userId]);
    return { assetId: id, status: 'uploaded', byteSize: actualSize };
  });

  app.post('/v1/memories', async (request, reply) => {
    const parsed = createMemorySchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_memory', message: parsed.error.issues[0]?.message ?? 'Invalid Memory.' } });
    const data = parsed.data;
    const userId = request.principal!.id;
    const headerValue = request.headers['idempotency-key'];
    const idempotencyKey = typeof headerValue === 'string' ? headerValue.trim().slice(0, 128) || null : null;
    if (idempotencyKey) {
      const existing = await pool.query('SELECT id FROM memories WHERE user_id=$1 AND idempotency_key=$2 AND deleted_at IS NULL', [userId, idempotencyKey]);
      if (existing.rowCount) return reply.code(200).send({ memory: await getMemory(userId, existing.rows[0]!.id as string), duplicate: true });
    }
    if (!await validateOwnedIds(userId, data.spaceIds, 'spaces')) return reply.code(400).send({ error: { code: 'invalid_space', message: 'One or more Spaces do not belong to this account.' } });
    if (!await validateOwnedIds(userId, data.assetIds, 'assets')) return reply.code(400).send({ error: { code: 'invalid_asset', message: 'One or more uploads are unavailable or not complete.' } });

    const client = await pool.connect();
    let memoryId: string;
    try {
      await client.query('BEGIN');
      const inserted = await client.query(
        `INSERT INTO memories(user_id, kind, status, source_app, source_url, source_domain, title, description,
          user_note, content_text, capture_metadata, captured_at, idempotency_key)
         VALUES($1,$2,'queued',$3,$4,$5,$6,$7,$8,$9,$10::jsonb,COALESCE($11::timestamptz,now()),$12)
         ON CONFLICT (user_id,idempotency_key) DO NOTHING RETURNING id`,
        [userId, data.kind, data.sourceApp ?? null, data.sourceUrl ?? null, sourceDomain(data.sourceUrl), data.title ?? null,
          data.description ?? null, data.userNote ?? null, data.contentText ?? null, JSON.stringify(data.captureMetadata),
          data.capturedAt ?? null, idempotencyKey],
      );
      if (!inserted.rowCount) {
        await client.query('ROLLBACK');
        const existing = await pool.query('SELECT id FROM memories WHERE user_id=$1 AND idempotency_key=$2 AND deleted_at IS NULL', [userId, idempotencyKey]);
        return reply.code(200).send({ memory: await getMemory(userId, existing.rows[0]!.id as string), duplicate: true });
      }
      memoryId = inserted.rows[0]!.id as string;
      const spaceIds = unique(data.spaceIds);
      if (spaceIds.length) {
        await client.query(
          `INSERT INTO memory_spaces(memory_id, space_id, user_id, assigned_by)
           SELECT $1, id, $2, 'user' FROM spaces WHERE id=ANY($3::uuid[]) AND user_id=$2 AND deleted_at IS NULL`,
          [memoryId, userId, spaceIds],
        );
      }
      const assetIds = unique(data.assetIds);
      if (assetIds.length) {
        await client.query(
          `INSERT INTO memory_assets(memory_id, asset_id, user_id, role, position)
           SELECT $1, id, $2, CASE WHEN position=1 THEN 'original' ELSE 'attachment' END, position-1
           FROM unnest($3::uuid[]) WITH ORDINALITY AS input(id, position)
           WHERE EXISTS (SELECT 1 FROM assets a WHERE a.id=input.id AND a.user_id=$2 AND a.status='uploaded')`,
          [memoryId, userId, assetIds],
        );
        await client.query("UPDATE assets SET status='attached' WHERE id=ANY($1::uuid[]) AND user_id=$2", [assetIds, userId]);
      }
      await enqueueMemoryProcessing(client, userId, memoryId);
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK').catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    const memory = await getMemory(userId, memoryId!);
    return reply.code(201).send({ memory });
  });

  app.get('/v1/memories', async (request, reply) => {
    const query = request.query as { limit?: string; cursor?: string; kind?: string; spaceId?: string; source?: string; after?: string; before?: string };
    const limit = Math.min(100, Math.max(1, Number(query.limit) || 30));
    if (query.kind && !memoryKinds.includes(query.kind as typeof memoryKinds[number])) {
      return reply.code(400).send({ error: { code: 'invalid_kind', message: 'Unknown Memory type.' } });
    }
    const cursor = decodeCursor(query.cursor);
    if (query.cursor && !cursor) return reply.code(400).send({ error: { code: 'invalid_cursor', message: 'The page cursor is invalid.' } });
    const after = query.after && !Number.isNaN(Date.parse(query.after)) ? new Date(query.after).toISOString() : null;
    const before = query.before && !Number.isNaN(Date.parse(query.before)) ? new Date(query.before).toISOString() : null;
    if ((query.after && !after) || (query.before && !before)) return reply.code(400).send({ error: { code: 'invalid_date', message: 'The date filter is invalid.' } });
    const result = await pool.query(
      `SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
        m.description, m.user_note, m.page_text, m.ai_summary, m.visual_description, m.captured_at, m.created_at,
        (SELECT a.object_key FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id
         WHERE ma.memory_id=m.id AND ma.user_id=m.user_id ORDER BY ma.position LIMIT 1) AS preview_key
       FROM memories m
       WHERE m.user_id=$1 AND m.deleted_at IS NULL
         AND ($2::memory_kind IS NULL OR m.kind=$2::memory_kind)
         AND ($3::uuid IS NULL OR EXISTS (SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$3 AND ms.user_id=m.user_id))
         AND ($4::text IS NULL OR m.source_domain=$4)
         AND ($5::timestamptz IS NULL OR (m.captured_at,m.id)<($5::timestamptz,$6::uuid))
         AND ($8::timestamptz IS NULL OR m.captured_at >= $8::timestamptz)
         AND ($9::timestamptz IS NULL OR m.captured_at < $9::timestamptz)
       ORDER BY m.captured_at DESC, m.id DESC LIMIT $7`,
      [request.principal!.id, query.kind ?? null, query.spaceId ?? null, query.source ?? null,
        cursor?.capturedAt.toISOString() ?? null, cursor?.id ?? null, limit + 1, after, before],
    );
    const hasMore = result.rows.length > limit;
    const rows = result.rows.slice(0, limit);
    const items = await Promise.all(rows.map(async (row) => ({
      id: row.id, kind: row.kind, status: row.status, sourceApp: row.source_app, sourceUrl: row.source_url,
      sourceDomain: row.source_domain, title: row.title, description: row.description,
      userNote: row.user_note, pageText: row.page_text, summary: row.ai_summary, visualDescription: row.visual_description,
      capturedAt: row.captured_at, createdAt: row.created_at,
      previewUrl: row.preview_key ? await createReadUrl(row.preview_key) : null,
    })));
    const last = rows.at(-1);
    return { memories: items, nextCursor: hasMore && last ? encodeCursor(last.captured_at, last.id) : null };
  });

  app.get('/v1/memories/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.principal!.id;
    const memory = await getMemory(userId, id);
    if (!memory) return reply.code(404).send({ error: { code: 'memory_not_found', message: 'Memory not found.' } });
    await pool.query('UPDATE memories SET last_opened_at=now() WHERE id=$1 AND user_id=$2', [id, userId]);
    await pool.query("INSERT INTO memory_events(user_id,memory_id,event_type) VALUES($1,$2,'opened')", [userId, id]);
    return { memory };
  });

  app.patch('/v1/memories/:id', async (request, reply) => {
    const parsed = updateMemorySchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_memory_update', message: parsed.error.issues[0]?.message ?? 'Invalid update.' } });
    const { id } = request.params as { id: string };
    const userId = request.principal!.id;
    const patch = parsed.data;
    if (patch.spaceIds && !await validateOwnedIds(userId, patch.spaceIds, 'spaces')) {
      return reply.code(400).send({ error: { code: 'invalid_space', message: 'One or more Spaces do not belong to this account.' } });
    }
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      const updated = await client.query(
        `UPDATE memories SET title=CASE WHEN $3 THEN $4 ELSE title END,
          user_note=CASE WHEN $5 THEN $6 ELSE user_note END, updated_at=now()
         WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL RETURNING id`,
        [id, userId, 'title' in patch, patch.title ?? null, 'userNote' in patch, patch.userNote ?? null],
      );
      if (!updated.rowCount) {
        await client.query('ROLLBACK');
        return reply.code(404).send({ error: { code: 'memory_not_found', message: 'Memory not found.' } });
      }
      if (patch.spaceIds) {
        await client.query('DELETE FROM memory_spaces WHERE memory_id=$1 AND user_id=$2', [id, userId]);
        const spaceIds = unique(patch.spaceIds);
        if (spaceIds.length) {
          await client.query(
            `INSERT INTO memory_spaces(memory_id,space_id,user_id,assigned_by)
             SELECT $1,id,$2,'user' FROM spaces WHERE id=ANY($3::uuid[]) AND user_id=$2 AND deleted_at IS NULL`,
            [id, userId, spaceIds],
          );
        }
      }
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK').catch(() => undefined);
      throw error;
    } finally { client.release(); }
    return { memory: await getMemory(userId, id) };
  });

  app.delete('/v1/memories/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query(
      "UPDATE memories SET deleted_at=now(), updated_at=now() WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL RETURNING id",
      [id, request.principal!.id],
    );
    if (!result.rowCount) return reply.code(404).send({ error: { code: 'memory_not_found', message: 'Memory not found.' } });
    return reply.code(204).send();
  });

  app.post('/v1/memories/:id/restore', async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.principal!.id;
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      await client.query(
        'SELECT memory_id FROM memory_processing_jobs WHERE memory_id=$1 AND user_id=$2 FOR UPDATE',
        [id, userId],
      );
      const result = await client.query<{ status: string }>(
        'UPDATE memories SET deleted_at=NULL, updated_at=now() WHERE id=$1 AND user_id=$2 AND deleted_at IS NOT NULL RETURNING status',
        [id, userId],
      );
      if (!result.rowCount) {
        await client.query('ROLLBACK');
        return reply.code(404).send({ error: { code: 'deleted_memory_not_found', message: 'Deleted Memory not found.' } });
      }
      if (result.rows[0]!.status === 'queued' || result.rows[0]!.status === 'processing') {
        await client.query("UPDATE memories SET status='queued', processing_error=NULL WHERE id=$1 AND user_id=$2", [id, userId]);
        await enqueueMemoryProcessing(client, userId, id);
      }
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK').catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return { memory: await getMemory(userId, id) };
  });

  app.post('/v1/memories/:id/retry', async (request, reply) => {
    const { id } = request.params as { id: string };
    const userId = request.principal!.id;
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      await client.query(
        'SELECT memory_id FROM memory_processing_jobs WHERE memory_id=$1 AND user_id=$2 FOR UPDATE',
        [id, userId],
      );
      const result = await client.query(
        "UPDATE memories SET status='queued', processing_error=NULL WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL AND status='failed' RETURNING id",
        [id, userId],
      );
      if (!result.rowCount) {
        await client.query('ROLLBACK');
        return reply.code(409).send({ error: { code: 'memory_not_retryable', message: 'Only failed Memories can be retried.' } });
      }
      await enqueueMemoryProcessing(client, userId, id);
      await client.query('COMMIT');
    } catch (error) {
      await client.query('ROLLBACK').catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return { memory: await getMemory(userId, id) };
  });
}
