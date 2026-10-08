import * as FileSystem from 'expo-file-system/legacy';
import { downloadApiFile, discardDownload } from './download';
import { validateArchivePrefix } from './schemas/exports';
import { idSchema, parseRequest } from './schemas/common';

export async function downloadMarkdownArchive(spaceId?: string) {
  if (spaceId !== undefined) spaceId = parseRequest(idSchema, spaceId);
  const directory = FileSystem.cacheDirectory || FileSystem.documentDirectory;
  if (!directory) throw new Error('Trove could not prepare the export on this device.');

  const params = new URLSearchParams();
  if (spaceId) params.set('spaceId', spaceId);
  const encodedParams = params.toString();
  const query = encodedParams ? `?${encodedParams}` : '';
  const path = `${directory}trove-markdown-${spaceId || 'library'}-${Date.now()}.zip`;
  const uri = await downloadApiFile(`/v1/export/markdown${query}`, path, 'application/zip');
  try {
    const prefix = await FileSystem.readAsStringAsync(uri, {
      encoding: FileSystem.EncodingType.Base64, position: 0, length: 4,
    });
    validateArchivePrefix(prefix);
    return uri;
  } catch (error) {
    await discardDownload(uri);
    throw error;
  }
}
