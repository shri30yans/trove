import * as FileSystem from 'expo-file-system/legacy';
import { logSync } from '../../utils/sync-log';
import type { MemoryCapture } from '../../types';

export async function preserveOfflineAssets(capture: MemoryCapture, localId: string) {
  if (!capture.attachments?.length) return capture;
  if (!FileSystem.documentDirectory) throw new Error('Local file storage is not available on this device.');
  const directory = `${FileSystem.documentDirectory}pending-captures/`;
  await FileSystem.makeDirectoryAsync(directory, { intermediates: true });
  const attachments: NonNullable<MemoryCapture['attachments']> = [];
  try {
    for (const [index, attachment] of capture.attachments.entries()) {
      const safeName = attachment.asset.filename.replace(/[^a-zA-Z0-9._-]/g, '_');
      const destination = `${directory}${localId}-${index}-${safeName}`;
      attachments.push({ ...attachment, asset: { ...attachment.asset, uri: destination } });
      await FileSystem.copyAsync({ from: attachment.asset.uri, to: destination });
    }
  } catch (error) {
    await deleteOfflineAssets({ localId, capture: { ...capture, attachments } }).catch(() => logSync('queue.uncommitted-cleanup-failed', { localId }));
    throw error;
  }
  return { ...capture, attachments };
}

export async function deleteOfflineAssets(entry: { localId: string; capture: MemoryCapture }) {
  if (!FileSystem.documentDirectory) throw new Error('Local file storage is not available on this device.');
  const copiedFilePrefix = `${FileSystem.documentDirectory}pending-captures/${entry.localId}-`;
  const copiedAssets = entry.capture.attachments?.map(({ asset }) => asset.uri)
    .filter((uri) => uri.startsWith(copiedFilePrefix)) ?? [];
  await Promise.all(copiedAssets.map(async (uri) => {
    try {
      await FileSystem.deleteAsync(uri, { idempotent: true });
    } catch (error) {
      logSync('queue.asset-cleanup-failed', { localId: entry.localId });
      throw error;
    }
  }));
}
