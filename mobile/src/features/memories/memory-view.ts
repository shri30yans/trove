import type { z } from 'zod';
import type { assetSchema, memoryDetailSchema, memorySpaceSchema } from '../../api/schemas/memories';

export type MemorySpace = z.infer<typeof memorySpaceSchema>;
type RemoteAsset = z.infer<typeof assetSchema>;
export type MemoryAsset = Omit<RemoteAsset, 'status' | 'createdAt'> & { status: RemoteAsset['status'] | 'queued'; createdAt?: string };
type Detail = z.infer<typeof memoryDetailSchema>;
/** Presentation accepts list cards, detail records and locally queued captures.
 * Endpoint schemas validate each projection's required fields before rendering. */
export type Memory = Pick<Detail, 'id' | 'kind' | 'capturedAt'> & Partial<Omit<Detail, 'id' | 'kind' | 'capturedAt' | 'assets'>> & {
  assets?: MemoryAsset[]; previewUrl?: string | null; matchExcerpt?: string | null;
  similarity?: number; reason?: string;
  localPending?: boolean; localSyncState?: 'queued' | 'uploading' | 'retrying' | 'blocked';
  localSyncMessage?: string; localRetryAt?: number; replacesLocalId?: string; localAssetUri?: string;
};
