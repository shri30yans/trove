import * as FileSystem from 'expo-file-system/legacy';
import { apiFailureCode, apiFailureMessage } from './messages';
import { logSync } from '../utils/sync-log';
import { ApiError, getAccessToken, getApiUrl, request } from './client';
import { requestBody, parseContract } from './schemas/common';
import { uploadRequestSchema, uploadResponseSchema, uploadContentResponseSchema, uploadCompleteSchema, createMemorySchema } from './schemas/uploads';
import { memoryResponseSchema } from './schemas/memories';
import type { CaptureAsset, MemoryCapture } from '../types';

export class CaptureFileError extends Error {}

async function uploadAsset(asset: CaptureAsset) {
  const info = await FileSystem.getInfoAsync(asset.uri);
  if (!info.exists) throw new CaptureFileError('The local file is missing. Choose the file again to save it.');
  const byteSize = info.size;
  if (!Number.isSafeInteger(byteSize) || byteSize <= 0) throw new CaptureFileError('The file is empty. Choose a non-empty file to save it.');
  const upload = await request('/v1/uploads', uploadResponseSchema, {
    method: 'POST',
    body: requestBody(uploadRequestSchema, { filename: asset.filename, mimeType: asset.mimeType, byteSize }),
  });
  const token = await getAccessToken();
  logSync('upload.started', { assetId: upload.assetId, bytes: byteSize, transport: 'api' });
  const task = FileSystem.createUploadTask(getApiUrl(upload.uploadPath), asset.uri, {
    httpMethod: upload.method,
    uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
    headers: { ...upload.headers, Authorization: `Bearer ${token}` },
    sessionType: FileSystem.FileSystemSessionType.FOREGROUND,
  });
  try {
    const uploaded = await task.uploadAsync();
    if (!uploaded || uploaded.status < 200 || uploaded.status >= 300) {
      logSync('upload.rejected', { assetId: upload.assetId, status: uploaded?.status ?? 0 });
      let code: string | undefined;
      if (uploaded?.body) {
        try { code = apiFailureCode(JSON.parse(uploaded.body)); }
        catch { /* Non-JSON responses use status-based user copy. */ }
      }
      const status = uploaded?.status ?? 503;
      throw new ApiError(apiFailureMessage(status, code), status, code);
    }
    let acknowledgement: unknown;
    try { acknowledgement = JSON.parse(uploaded.body); } catch { throw new Error('Trove returned an unreadable upload acknowledgement.'); }
    parseContract(uploadContentResponseSchema.refine((result) => result.assetId === upload.assetId && result.byteSize === byteSize), acknowledgement);
    logSync('upload.transferred', { assetId: upload.assetId, status: uploaded.status });
  } catch (error) {
    logSync('upload.failed', { assetId: upload.assetId, errorType: error instanceof Error ? error.name : 'unknown' });
    throw error;
  }
  await request(`/v1/uploads/${upload.assetId}/complete`, uploadCompleteSchema.refine((result) => result.assetId === upload.assetId && result.byteSize === byteSize), { method: 'POST', body: '{}' });
  logSync('upload.completed', { assetId: upload.assetId });
  return upload.assetId;
}

type CaptureSubmission = {
  key: string;
  assetIds: string[];
  onUploaded: (ids: string[]) => Promise<void>;
};

export async function submitCapture(capture: MemoryCapture & { capturedAt: string }, { key, assetIds: uploadedAssetIds, onUploaded }: CaptureSubmission) {
  const assetIds = [...uploadedAssetIds];
  for (const attachment of (capture.attachments ?? []).slice(assetIds.length)) {
    assetIds.push(await uploadAsset(attachment.asset));
    await onUploaded([...assetIds]);
  }
  const { attachments: _attachments, ...memory } = capture;
  logSync('memory.submitting', { key, attachments: assetIds.length });
  const result = await request('/v1/memories', memoryResponseSchema, {
    method: 'POST',
    headers: { 'Idempotency-Key': key },
    body: requestBody(createMemorySchema, { ...memory, captureMetadata: memory.captureMetadata ?? {}, assetIds, spaceIds: memory.spaceIds ?? [] }),
  });
  logSync('memory.confirmed', { key, memoryId: result.memory.id });
  return result.memory;
}
