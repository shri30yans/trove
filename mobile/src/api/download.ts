import * as FileSystem from 'expo-file-system/legacy';
import { ApiError, getAccessToken, getApiUrl, refreshAccessToken } from './client';
import { apiFailureCode, apiFailureMessage, CONNECTION_MESSAGE } from './messages';
import { validateBinaryDownload } from './schemas/binary';

/** Cleanup is ancillary: retain the transfer/contract error if removing its partial file fails. */
export async function discardDownload(uri: string): Promise<void> {
  try { await FileSystem.deleteAsync(uri, { idempotent: true }); }
  catch { console.warn('[Trove download]', { stage: 'partial-file-cleanup-failed' }); }
}

export async function downloadApiFile(path: string, target: string, mimeType: string): Promise<string> {
  const url = getApiUrl(path);
  for (let attempt = 0; attempt < 2; attempt++) {
    const token = attempt === 0 ? await getAccessToken() : await refreshAccessToken();
    let result: FileSystem.FileSystemDownloadResult;
    try {
      result = await FileSystem.downloadAsync(url, target, { headers: { Accept: mimeType, Authorization: `Bearer ${token}` } });
    } catch (cause) {
      await discardDownload(target);
      throw new Error(CONNECTION_MESSAGE, { cause });
    }
    if (result.status === 200) {
      try {
        validateBinaryDownload(result, await FileSystem.getInfoAsync(result.uri), mimeType);
        return result.uri;
      } catch (error) {
        await discardDownload(result.uri);
        throw error;
      }
    }
    let code: string | undefined;
    if (result.status !== 401) {
      try { code = apiFailureCode(JSON.parse(await FileSystem.readAsStringAsync(result.uri))); }
      catch { /* Non-JSON failures use status-based copy. */ }
    }
    await discardDownload(result.uri);
    if (result.status === 401 && attempt === 0) continue;
    throw new ApiError(apiFailureMessage(result.status, code), result.status, code);
  }
  throw new ApiError('Your session expired. Sign in again.', 401);
}
