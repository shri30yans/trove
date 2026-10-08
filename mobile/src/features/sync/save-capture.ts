import { randomUUID } from 'expo-crypto';
import { captureSchema, type PendingCapture } from '../../domain/pending-capture';
import type { MemoryCapture } from '../../types';
import { insertPendingCapture } from '../../storage/capture-outbox';
import { preserveOfflineAssets, deleteOfflineAssets } from './capture-files';
import { logSync } from '../../utils/sync-log';

export async function queueOfflineCapture(capture: MemoryCapture) {
  const parsed = captureSchema.safeParse(capture);
  if (!parsed.success) throw new Error('Could not save this item: capture details are missing or invalid.');
  capture = parsed.data;
  const localId = `${Date.now()}-${randomUUID()}`;
  const preserved = await preserveOfflineAssets(capture, localId);
  const entry: PendingCapture = { key: localId, localId, attempts: 0, retryAt: 0, blocked: false, assetIds: [], capture: { ...preserved, capturedAt: capture.capturedAt ?? new Date().toISOString() } };
  try {
    await insertPendingCapture(entry);
  } catch (error) {
    await deleteOfflineAssets(entry).catch(() => logSync('queue.uncommitted-cleanup-failed', { localId }));
    throw error;
  }
  logSync('queue.saved', { localId, attachments: capture.attachments?.length ?? 0 });
  return entry;
}
