import { getAcknowledgedCaptures, getPendingCaptures, clearCaptureOutbox } from '../../storage/capture-outbox';
import { deleteOfflineAssets } from './capture-files';

export async function deleteLocalCaptures() {
  const entries = [...await getPendingCaptures(), ...await getAcknowledgedCaptures()];
  for (const entry of entries) await deleteOfflineAssets(entry);
  await clearCaptureOutbox();
}
