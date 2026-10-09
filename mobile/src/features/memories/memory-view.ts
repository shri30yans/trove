import type { z } from 'zod';
import type {
  assetSchema,
  memoryCardSchema,
  memoryDetailSchema,
  memorySpaceSchema,
} from '../../api/schemas/memories';

export type MemorySpace = z.infer<typeof memorySpaceSchema>;
type RemoteAsset = z.infer<typeof assetSchema>;
export type MemoryAsset = Omit<RemoteAsset, 'status' | 'createdAt'> & { status: RemoteAsset['status'] | 'queued'; createdAt?: string };
type Detail = z.infer<typeof memoryDetailSchema>;
/** The card every remote projection answers with, so a row never guards what no endpoint omits. */
type Card = z.infer<typeof memoryCardSchema>;
/** A Memory as the UI holds it: the guaranteed card, the fields only the detail projection
 * returns, and the sync state the local queue attaches before the API has seen the capture. */
export type Memory = Card & Partial<Omit<Detail, keyof Card | 'assets'>> & {
  assets?: MemoryAsset[]; previewUrl?: string | null; matchExcerpt?: string | null;
  similarity?: number; reason?: string;
  localPending?: boolean; localSyncState?: 'queued' | 'uploading' | 'retrying' | 'blocked';
  localSyncMessage?: string; localRetryAt?: number; replacesLocalId?: string; localAssetUri?: string;
};
