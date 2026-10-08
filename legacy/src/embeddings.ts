import { config } from './config.js';

export const EMBEDDING_DIMENSIONS = 768;
const MAX_TEXT_CHARACTERS = 24_000;
const MAX_IMAGE_BYTES = 52_428_800;
const MODEL_CACHE_MS = 30_000;

export type TextEmbeddingPurpose = 'query' | 'document';
export type EmbeddingInput =
  | { modality: 'text'; text: string; purpose: TextEmbeddingPurpose }
  | { modality: 'image'; bytes: Buffer; mimeType: string };

export type EmbeddingModel = { modelId: string; revision: string };
export type EmbeddingModels = {
  ready: true;
  dimensions: typeof EMBEDDING_DIMENSIONS;
  spaceId: string;
  text: EmbeddingModel;
  image: EmbeddingModel;
};

export type Embedding = {
  modality: EmbeddingInput['modality'];
  spaceId: string;
  modelId: string;
  modelRevision: string;
  vector: number[];
};

export class EmbeddingClientError extends Error {
  constructor(message: string, public readonly status: number | null = null) {
    super(message);
    this.name = 'EmbeddingClientError';
  }
}

type ServiceEmbedding = { model?: unknown; revision?: unknown; spaceId?: unknown; embedding?: unknown };
type ServiceModels = {
  ready?: unknown;
  dimensions?: unknown;
  spaceId?: unknown;
  textModel?: unknown;
  textRevision?: unknown;
  visionModel?: unknown;
  visionRevision?: unknown;
};

/** The only application client for text and image embedding inference. */
class EmbeddingClient {
  private readonly baseUrl = config.NOMIC_EMBEDDING_SERVICE_URL.replace(/\/$/, '');
  private cachedModels: EmbeddingModels | null = null;
  private modelCacheExpiresAt = 0;

  async embed(input: EmbeddingInput): Promise<Embedding> {
    const models = await this.models();
    if (!models) throw new EmbeddingClientError('The local embedding service is not ready.');

    if (input.modality === 'text' && !input.text.trim()) {
      throw new EmbeddingClientError('Text embeddings require non-empty text.');
    }
    if (input.modality === 'image' && (!input.bytes.length || input.bytes.length > MAX_IMAGE_BYTES)) {
      throw new EmbeddingClientError('Image embeddings require a non-empty image under 50 MiB.');
    }
    if (input.modality === 'image' && !input.mimeType.startsWith('image/')) {
      throw new EmbeddingClientError('Image embeddings require an image MIME type.');
    }

    const endpoint = input.modality === 'text' ? '/v1/embeddings/text' : '/v1/embeddings/image';
    const body: BodyInit = input.modality === 'text'
      ? JSON.stringify({ text: input.text.slice(0, MAX_TEXT_CHARACTERS), purpose: input.purpose })
      : new Blob([Uint8Array.from(input.bytes)], { type: input.mimeType });
    const contentType = input.modality === 'text' ? 'application/json' : input.mimeType;
    const timeoutMs = input.modality === 'text' ? 30_000 : 120_000;

    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': contentType,
          Accept: 'application/json',
          ...(config.NOMIC_SERVICE_TOKEN ? { Authorization: `Bearer ${config.NOMIC_SERVICE_TOKEN}` } : {}),
        },
        body,
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      throw new EmbeddingClientError(error instanceof Error ? error.message : 'The local embedding service is unavailable.');
    }
    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new EmbeddingClientError(detail.slice(0, 500) || 'The local embedding service could not create an embedding.', response.status);
    }

    let payload: ServiceEmbedding;
    try {
      payload = await response.json() as ServiceEmbedding;
    } catch {
      throw new EmbeddingClientError('The local embedding service returned invalid JSON.');
    }

    const expected = input.modality === 'text' ? models.text : models.image;
    if (payload.model !== expected.modelId || payload.revision !== expected.revision || payload.spaceId !== models.spaceId) {
      this.invalidateModels();
      throw new EmbeddingClientError('The local embedding service returned a model outside the active embedding space.');
    }
    if (!Array.isArray(payload.embedding) || payload.embedding.length !== EMBEDDING_DIMENSIONS ||
        payload.embedding.some((value) => typeof value !== 'number' || !Number.isFinite(value))) {
      throw new EmbeddingClientError(`Expected a finite ${EMBEDDING_DIMENSIONS}-dimensional vector.`);
    }
    const vector = payload.embedding as number[];
    const magnitude = Math.hypot(...vector);
    if (magnitude < 0.999 || magnitude > 1.001) {
      throw new EmbeddingClientError('The local embedding service returned a vector that was not L2-normalized.');
    }
    return {
      modality: input.modality,
      spaceId: models.spaceId,
      modelId: expected.modelId,
      modelRevision: expected.revision,
      vector,
    };
  }

  async models(timeoutMs = 1_000, forceRefresh = false): Promise<EmbeddingModels | null> {
    if (!forceRefresh && this.cachedModels && Date.now() < this.modelCacheExpiresAt) return this.cachedModels;
    try {
      const response = await fetch(`${this.baseUrl}/health/ready`, { signal: AbortSignal.timeout(timeoutMs) });
      if (!response.ok) return null;
      const body = await response.json() as ServiceModels;
      if (body.ready !== true || body.dimensions !== EMBEDDING_DIMENSIONS ||
          typeof body.spaceId !== 'string' || !body.spaceId ||
          typeof body.textModel !== 'string' || typeof body.textRevision !== 'string' ||
          typeof body.visionModel !== 'string' || typeof body.visionRevision !== 'string') return null;
      const models: EmbeddingModels = {
        ready: true,
        dimensions: EMBEDDING_DIMENSIONS,
        spaceId: body.spaceId,
        text: { modelId: body.textModel, revision: body.textRevision },
        image: { modelId: body.visionModel, revision: body.visionRevision },
      };
      this.cachedModels = models;
      this.modelCacheExpiresAt = Date.now() + MODEL_CACHE_MS;
      return models;
    } catch {
      return null;
    }
  }

  async isReady(timeoutMs = 1_000) {
    return (await this.models(timeoutMs)) !== null;
  }

  private invalidateModels() {
    this.cachedModels = null;
    this.modelCacheExpiresAt = 0;
  }
}

export const embeddings = new EmbeddingClient();

export function vectorLiteral(vector: number[]) {
  return `[${vector.join(',')}]`;
}
