import NetInfo from '@react-native-community/netinfo';
import { ApiError } from '../../api/client';
import { CaptureFileError, submitCapture } from '../../api/captures';
import { acknowledgeCapture, finishCaptureCleanup, getAcknowledgedCaptures, getPendingCaptures, updatePendingCapture } from '../../storage/capture-outbox';
import { logSync } from '../../utils/sync-log';
import type { Memory } from '../../types';
import type { PendingCapture } from '../../domain/pending-capture';
import { deleteOfflineAssets } from './capture-files';

let syncFlight: ReturnType<typeof runSync> | null = null;

async function cleanupAcknowledgedCapture(entry: PendingCapture) {
  try {
    await deleteOfflineAssets(entry);
    await finishCaptureCleanup(entry.localId);
  } catch {
    logSync('queue.cleanup-deferred', { localId: entry.localId });
  }
}

export async function cleanupDeliveredCaptures() {
  for (const entry of await getAcknowledgedCaptures()) await cleanupAcknowledgedCapture(entry);
}

export type SyncOptions = {
  force?: boolean;
  onUploading?: (localId: string | null) => void;
  onSynced?: (item: { localId: string; memory: Memory }) => void;
  shouldContinue?: () => boolean;
};

export function syncPendingCaptures(options: SyncOptions = {}) {
  if (syncFlight) return syncFlight;
  syncFlight = runSync(options).finally(() => { syncFlight = null; });
  return syncFlight;
}

async function runSync({ force = false, onUploading, onSynced, shouldContinue }: SyncOptions) {
  const synced: { localId: string; memory: Memory }[] = [];
  await cleanupDeliveredCaptures();
  const state = await NetInfo.fetch();
  logSync('queue.started', { force, connected: state.isConnected, reachable: state.isInternetReachable });
  if (!state.isConnected || state.isInternetReachable === false) {
    return { synced, remaining: (await getPendingCaptures()).length, offline: true };
  }
  const pending = await getPendingCaptures();
  for (const entry of [...pending].reverse()) {
    if (shouldContinue && !shouldContinue()) break;
    if (!force && (entry.blocked || (entry.retryAt) > Date.now())) continue;
    logSync('queue.attempt', { localId: entry.localId, attempt: (entry.attempts) + 1, completedFiles: entry.assetIds.length });
    onUploading?.(`local-${entry.localId}`);
    let memory: Memory;
    try {
      memory = await submitCapture(entry.capture, { key: entry.key, assetIds: entry.assetIds, onUploaded: async (assetIds) => {
        await updatePendingCapture(entry.localId, { assetIds });
      } });
    } catch (error) {
      const attempts = (entry.attempts) + 1;
      const blocked = error instanceof CaptureFileError || (error instanceof ApiError && error.status >= 400 && error.status < 500
        && ![408, 429].includes(error.status));
      logSync('queue.failed', { localId: entry.localId, attempt: attempts, blocked, status: error instanceof ApiError ? error.status : undefined, errorType: error instanceof Error ? error.name : 'unknown' });
      await updatePendingCapture(entry.localId, {
        attempts, blocked,
        lastError: error instanceof Error ? error.message : 'Could not sync this save.',
        retryAt: Date.now() + Math.min(300_000, 5_000 * 2 ** Math.min(attempts - 1, 6) * (0.8 + Math.random() * 0.4)),
      });
      onUploading?.(null);
      continue;
    }
    // Commit the acknowledgement before deleting the only local copy of attachments.
    // If persistence fails, keep files and retry with the same idempotency key.
    await acknowledgeCapture(entry.localId);
    logSync('queue.acknowledged', { localId: entry.localId, memoryId: memory.id });
    const item = { localId: `local-${entry.localId}`, memory };
    synced.push(item);
    try { onSynced?.(item); } catch { logSync('queue.observer-failed', { localId: entry.localId }); }
    onUploading?.(null);
    await cleanupAcknowledgedCapture(entry);
  }
  return { synced, remaining: (await getPendingCaptures()).length, offline: false };
}
