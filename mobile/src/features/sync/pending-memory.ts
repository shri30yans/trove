import type { Memory } from '../../types';
import type { PendingCapture } from '../../domain/pending-capture';

export function pendingMemory(entry: PendingCapture): Memory {
  const firstAsset = entry.capture.attachments?.[0]?.asset;
  return {
    id: `local-${entry.localId}`,
    kind: entry.capture.kind,
    status: 'queued',
    title: entry.capture.title || entry.capture.contentText?.split('\n')[0] || entry.capture.userNote?.split('\n')[0] || firstAsset?.filename || 'Saved memory',
    description: entry.capture.description || entry.capture.contentText || entry.capture.userNote || null,
    userNote: entry.capture.userNote || null,
    contentText: entry.capture.contentText || null,
    sourceUrl: entry.capture.sourceUrl || null,
    sourceApp: entry.capture.sourceApp || null,
    capturedAt: entry.capture.capturedAt,
    spaces: [],
    assets: (entry.capture.attachments || []).map((attachment, index) => ({
      id: `local-${entry.localId}-${index}`,
      filename: attachment.asset.filename,
      mimeType: attachment.asset.mimeType,
      byteSize: attachment.asset.byteSize ?? null,
      status: 'queued',
      role: 'attachment',
      url: attachment.asset.uri,
    })),
    localPending: true,
    localAssetUri: firstAsset?.uri,
  };
}
