import { pool } from './db/pool.js';
import { aiAvailable, describeMemory, transcribeAudio, type MemoryInput } from './ai.js';
import { embeddings, type Embedding } from './embeddings.js';
import { saveAssetEmbedding, saveMemoryEmbedding } from './embedding-store.js';
import { completeMissingMemoryJob } from './queue.js';
import { readObject } from './storage.js';
import { extractPublicPage } from './url-extract.js';

type MemoryRow = {
  id: string;
  user_id: string;
  kind: string;
  title: string | null;
  description: string | null;
  user_note: string | null;
  content_text: string | null;
  source_url: string | null;
  source_domain: string | null;
  ai_processing_enabled: boolean;
};

type AssetRow = {
  id: string;
  object_key: string;
  original_filename: string | null;
  mime_type: string;
  checksum_sha256: string | null;
};

export async function processMemory(memoryId: string, userId: string, leaseToken: string): Promise<void> {
  const memoryResult = await pool.query<MemoryRow>(
    `SELECT m.id, m.user_id, m.kind, m.title, m.description, m.user_note, m.content_text, m.source_url,
            m.source_domain, COALESCE(p.ai_processing_enabled, false) AS ai_processing_enabled
     FROM memories m LEFT JOIN user_preferences p ON p.user_id = m.user_id
     WHERE m.id = $1 AND m.user_id = $2 AND m.deleted_at IS NULL`,
    [memoryId, userId],
  );
  const memory = memoryResult.rows[0];
  if (!memory) {
    await completeMissingMemoryJob(memoryId, userId, leaseToken);
    return;
  }

  let page: Awaited<ReturnType<typeof extractPublicPage>> | null = null;
  if (memory.source_url && memory.kind === 'link') {
    try { page = await extractPublicPage(memory.source_url); } catch { page = null; }
  }
  const assetsResult = await pool.query<AssetRow>(
    `SELECT a.id, a.object_key, a.original_filename, a.mime_type, a.checksum_sha256
     FROM assets a JOIN memory_assets ma ON ma.asset_id = a.id
     WHERE ma.memory_id = $1 AND ma.user_id = $2 ORDER BY ma.position`,
    [memoryId, userId],
  );
  const assets = assetsResult.rows;
  const byteCache = new Map<string, Buffer>();
  const readAsset = async (asset: AssetRow) => {
    let bytes = byteCache.get(asset.id);
    if (!bytes) {
      bytes = await readObject(asset.object_key);
      byteCache.set(asset.id, bytes);
    }
    return bytes;
  };

  const input: MemoryInput = {
    kind: memory.kind,
    title: memory.title,
    description: memory.description,
    userNote: memory.user_note,
    contentText: [memory.content_text, page?.text].filter(Boolean).join('\n\n') || null,
    sourceDomain: memory.source_domain,
  };
  let ocrText: string | null = null;
  let transcript: string | null = null;
  let visualDescription: string | null = null;
  let summary: string | null = null;
  let topics: Array<{ name: string; confidence: number }> = [];
  let entities: Array<{ kind: string; value: string; normalizedValue?: string; confidence: number; properties?: Record<string, unknown> }> = [];

  if (memory.ai_processing_enabled && aiAvailable()) {
    const firstAsset = assets[0];
    const fileBuffer = firstAsset && ['image/', 'audio/'].some((prefix) => firstAsset.mime_type.startsWith(prefix))
      ? await readAsset(firstAsset)
      : undefined;
    if (firstAsset?.mime_type.startsWith('audio/') && fileBuffer) {
      transcript = await transcribeAudio(fileBuffer, firstAsset.original_filename ?? 'voice-memo', firstAsset.mime_type);
      input.contentText = [input.contentText, transcript].filter(Boolean).join('\n\n');
    }
    const enrichment = await describeMemory(
      input,
      firstAsset?.mime_type.startsWith('image/') && fileBuffer
        ? { buffer: fileBuffer, mimeType: firstAsset.mime_type }
        : undefined,
    );
    ocrText = enrichment.ocrText;
    visualDescription = enrichment.visualDescription;
    summary = enrichment.summary;
    topics = enrichment.topics;
    entities = enrichment.entities;
  }

  let memoryEmbedding: Embedding | null = null;
  const assetEmbeddings: Array<{ asset: AssetRow; embedding: Embedding }> = [];
  if (memory.ai_processing_enabled) {
    const searchableText = [
      memory.title ?? page?.title,
      memory.description ?? page?.description,
      memory.user_note,
      memory.content_text,
      page?.text,
      ocrText,
      transcript,
      summary,
      visualDescription,
    ].filter(Boolean).join('\n').trim();

    if (searchableText) {
      memoryEmbedding = await embeddings.embed({ modality: 'text', text: searchableText, purpose: 'document' });
    }
    for (const asset of assets) {
      if (!asset.mime_type.startsWith('image/')) continue;
      const bytes = await readAsset(asset);
      const embedding = await embeddings.embed({ modality: 'image', bytes, mimeType: asset.mime_type });
      assetEmbeddings.push({ asset, embedding });
    }
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const lease = await client.query(
      `SELECT 1 FROM memory_processing_jobs
       WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid
       FOR UPDATE`,
      [memoryId, userId, leaseToken],
    );
    if (!lease.rowCount) {
      await client.query('ROLLBACK');
      return;
    }
    const updated = await client.query(
      `UPDATE memories SET status = 'ready', title = COALESCE(title,$3), description = COALESCE(description,$4),
         page_text = $5, ocr_text = $6, transcript = $7,
         visual_description = $8, ai_summary = $9,
         processing_error = NULL, updated_at = now()
       WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL RETURNING id`,
      [memoryId, userId, page?.title ?? null, page?.description ?? null, page?.text ?? null,
        ocrText, transcript, visualDescription, summary],
    );
    if (!updated.rowCount) {
      await client.query(
        `UPDATE memory_processing_jobs
         SET status='completed', lease_token=NULL, lease_expires_at=NULL,
             last_error=NULL, updated_at=now()
         WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid`,
        [memoryId, userId, leaseToken],
      );
      await client.query('COMMIT');
      return;
    }
    if (memoryEmbedding) await saveMemoryEmbedding(client, userId, memoryId, memoryEmbedding);
    for (const { asset, embedding } of assetEmbeddings) {
      await saveAssetEmbedding(client, userId, asset.id, asset.checksum_sha256, embedding);
    }
    await client.query('DELETE FROM memory_topics WHERE memory_id=$1 AND user_id=$2', [memoryId, userId]);
    await client.query('DELETE FROM memory_entities WHERE memory_id=$1 AND user_id=$2 AND user_confirmed=false', [memoryId, userId]);
    for (const topic of topics) {
      await client.query(
        `INSERT INTO memory_topics(memory_id, user_id, topic, confidence) VALUES($1,$2,$3,$4)
         ON CONFLICT (memory_id, topic) DO UPDATE SET confidence = EXCLUDED.confidence`,
        [memoryId, userId, topic.name.toLowerCase(), topic.confidence],
      );
    }
    for (const entity of entities) {
      await client.query(
        `INSERT INTO memory_entities(memory_id, user_id, entity_kind, display_value, normalized_value, confidence, properties)
         VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)`,
        [memoryId, userId, entity.kind, entity.value, entity.normalizedValue ?? null, entity.confidence, JSON.stringify(entity.properties ?? {})],
      );
    }
    await client.query(
      `UPDATE memory_processing_jobs
       SET status='completed', lease_token=NULL, lease_expires_at=NULL,
           last_error=NULL, updated_at=now()
       WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid`,
      [memoryId, userId, leaseToken],
    );
    await client.query('COMMIT');
    return;
  } catch (error) {
    await client.query('ROLLBACK').catch(() => undefined);
    throw error;
  } finally {
    client.release();
  }
}
