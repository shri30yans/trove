import type { PendingCapture } from '../../domain/pending-capture';

export type SyncStatus = {
  state: 'loading' | 'complete' | 'uploading' | 'offline' | 'paused' | 'retrying' | 'blocked';
  message: string;
  detail?: string;
};

export function getSyncStatus({ ready, pending, uploadingId, online, automaticSync, error }: {
  ready: boolean; pending: PendingCapture[]; uploadingId: string | null;
  online: boolean; automaticSync: boolean; error: string | null;
}): SyncStatus {
  const count = `${pending.length} ${pending.length === 1 ? 'save' : 'saves'}`;
  if (error) return { state: 'blocked', message: error, detail: error };
  if (!ready) return { state: 'loading', message: 'Checking saves on this device…' };
  if (!pending.length) return { state: 'complete', message: 'All saves synced.' };
  if (uploadingId) return { state: 'uploading', message: `${count} remaining.` };
  const blocked = pending.filter((item) => item.blocked);
  if (blocked.length) return {
    state: 'blocked',
    message: `${blocked.length} ${blocked.length === 1 ? 'save needs' : 'saves need'} attention. ${blocked[0].lastError ?? 'Retry after resolving the issue.'}`,
    detail: blocked[0].lastError ?? 'Retry after resolving the issue.',
  };
  if (!automaticSync) return { state: 'paused', message: `${count} on this device. Sync manually or turn on automatic sync.` };
  if (!online) return { state: 'offline', message: `${count} on this device. Connect to the internet to sync.` };
  const failed = pending.find((item) => item.lastError);
  if (failed) return { state: 'retrying', message: `${count} on this device. Automatic sync will try again while Trove is open.` };
  return { state: 'retrying', message: `${count} waiting to sync.` };
}
