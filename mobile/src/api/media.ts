import * as FileSystem from 'expo-file-system/legacy';
import { getAccessToken, getApiUrl, refreshAccessToken, ApiError } from './client';
import { parseRequest } from './schemas/common';
import { localMediaUriSchema, mediaPathSchema } from './schemas/media';
import { validateBinaryResponse } from './schemas/binary';
import { downloadApiFile } from './download';
import { apiFailureMessage } from './messages';

export type MediaSource = { uri: string; headers?: Record<string, string> };
export async function mediaSource(path: string): Promise<MediaSource> {
  if (localMediaUriSchema.safeParse(path).success) return { uri: path };
  const validated = parseRequest(mediaPathSchema, path);
  return { uri: getApiUrl(validated), headers: { Authorization: `Bearer ${await getAccessToken()}` } };
}

export async function readMedia(path: string, mimeType: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const source = await mediaSource(path);
    const response = await fetch(source.uri, { headers: source.headers, signal, redirect: 'error' });
    if (response.status === 401 && attempt === 0) { await refreshAccessToken(); continue; }
    if (!response.ok) throw new ApiError(apiFailureMessage(response.status), response.status);
    const buffer = await response.arrayBuffer();
    if (!localMediaUriSchema.safeParse(path).success) {
      validateBinaryResponse({ status: response.status, headers: Object.fromEntries(response.headers.entries()) }, buffer.byteLength, mimeType);
    }
    return buffer;
  }
  throw new ApiError('Your session expired. Sign in again.', 401);
}

export async function downloadMedia(path: string, filename: string, mimeType: string): Promise<string> {
  if (localMediaUriSchema.safeParse(path).success) return path;
  parseRequest(mediaPathSchema, path);
  const directory = FileSystem.cacheDirectory ?? FileSystem.documentDirectory;
  if (!directory) throw new Error('Trove could not prepare this file on the device.');
  const target = `${directory}${filename.replace(/[^a-zA-Z0-9._-]/g, '_')}`;
  return downloadApiFile(path, target, mimeType);
}
