import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { getSyncStatus } from './sync-status';
import { subscribeLastAcknowledgedAt, subscribePendingCaptures } from '../../storage/capture-outbox';
import { pendingMemory } from './pending-memory';
import { cleanupDeliveredCaptures, syncPendingCaptures } from './deliver-captures';
import type { PendingCapture } from '../../domain/pending-capture';
import { logSync } from '../../utils/sync-log';
import type { Memory } from '../../types';

type QueueState = { state: 'loading'; items: PendingCapture[] } | { state: 'ready'; items: PendingCapture[] } | { state: 'error'; items: PendingCapture[]; error: string };
type WorkerState = { state: 'idle' } | { state: 'running'; uploadingId: string | null } | { state: 'error'; error: string };

export function useCaptureDelivery({ backgroundSync, localSettingsLoaded, showToast, onSynced, onDelivered }: {
  backgroundSync: boolean; localSettingsLoaded: boolean; showToast: (message: string) => void;
  onSynced: (localId: string, memory: Memory) => void; onDelivered: () => void;
}) {
  const [online, setOnline] = useState(false);
  const [queue, setQueue] = useState<QueueState>({ state: 'loading', items: [] });
  const [worker, setWorker] = useState<WorkerState>({ state: 'idle' });
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const pendingCaptures = queue.items;
  const pendingLoaded = queue.state === 'ready';
  const queueError = queue.state === 'error' ? queue.error : null;
  const syncing = worker.state === 'running';
  const uploadingId = worker.state === 'running' ? worker.uploadingId : null;
  const syncError = worker.state === 'error' ? worker.error : null;
  const [appActive, setAppActive] = useState(AppState.currentState === 'active');
  const pendingMemories = useMemo(() => pendingCaptures.map((entry) => ({
    ...pendingMemory(entry),
    localSyncState: uploadingId === `local-${entry.localId}` ? 'uploading' as const : entry.blocked ? 'blocked' as const : entry.lastError ? 'retrying' as const : 'queued' as const,
    localRetryAt: entry.lastError && !entry.blocked ? entry.retryAt : undefined,
    localSyncMessage: uploadingId === `local-${entry.localId}` ? 'Syncing this save…'
      : entry.lastError ?? (!backgroundSync ? 'Automatic sync is off. Sync from Profile when ready.'
        : 'Saved on this device. Waiting to sync while Trove is open and connected.'),
  })), [pendingCaptures, uploadingId, backgroundSync]);
  const syncInFlight = useRef<Promise<void> | null>(null);
  const syncPolicy = useRef(false);
  useEffect(() => {
    syncPolicy.current = localSettingsLoaded && backgroundSync && online && appActive;
    return () => { syncPolicy.current = false; };
  }, [localSettingsLoaded, backgroundSync, online, appActive]);

  useEffect(() => {
    if (appActive) void cleanupDeliveredCaptures().catch(() => logSync('queue.cleanup-deferred'));
  }, [appActive]);

  useEffect(() => subscribePendingCaptures((items) => {
    setQueue({ state: 'ready', items });
  }, (error) => {
    setQueue((current) => ({ state: 'error', items: current.items, error: error instanceof Error ? error.message : 'Could not read saves on this device.' }));
  }), []);

  useEffect(() => subscribeLastAcknowledgedAt(setLastSyncedAt, (error) => {
    setQueue((current) => ({ state: 'error', items: current.items, error: error instanceof Error ? error.message : 'Could not read sync history on this device.' }));
  }), []);

  const syncQueue = useCallback(async (notify = false) => {
    if (syncInFlight.current) return syncInFlight.current;
    const run = async () => {
      setWorker({ state: 'running', uploadingId: null });
      let syncedCount = 0;
      try {
        const result = await syncPendingCaptures({
          force: notify,
          shouldContinue: () => notify || syncPolicy.current,
          onUploading: (uploadingId) => setWorker({ state: 'running', uploadingId }),
          onSynced: ({ localId, memory }) => {
            syncedCount += 1;
            onSynced(localId, memory);
          },
        });
        setWorker({ state: 'idle' });
        if (notify && !result.offline && !result.remaining) {
          showToast(syncedCount ? `${syncedCount} ${syncedCount === 1 ? 'save' : 'saves'} synced.` : 'All saves synced.');
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Could not sync your saves.';
        setWorker({ state: 'error', error: message });
      } finally {
        syncInFlight.current = null;
        if (syncedCount) onDelivered();
      }
    };
    syncInFlight.current = run();
    await syncInFlight.current;
  }, [showToast, onSynced, onDelivered]);

  useEffect(() => {
    const remove = NetInfo.addEventListener((state) => {
      setOnline(!!state.isConnected && state.isInternetReachable !== false);
    });
    const appState = AppState.addEventListener('change', (state) => {
      setAppActive(state === 'active');
    });
    return () => { remove(); appState.remove(); };
  }, []);

  useEffect(() => {
    if (!pendingLoaded || !localSettingsLoaded || !backgroundSync || !online || !appActive || syncing || queueError || syncError) return;
    const eligible = pendingCaptures.filter((item) => !item.blocked);
    if (!eligible.length) return;
    const nextAttempt = Math.min(...eligible.map((item) => item.retryAt));
    const timer = setTimeout(() => void syncQueue(), Math.max(0, nextAttempt - Date.now()));
    return () => clearTimeout(timer);
  }, [pendingLoaded, localSettingsLoaded, backgroundSync, online, appActive, syncing, queueError, syncError, pendingCaptures, syncQueue]);

  const syncStatus = useMemo(() => getSyncStatus({
    ready: pendingLoaded && localSettingsLoaded,
    pending: pendingCaptures, uploadingId, online, automaticSync: backgroundSync,
    error: queueError ?? syncError,
  }), [pendingLoaded, localSettingsLoaded, pendingCaptures, uploadingId, online, backgroundSync, queueError, syncError]);

  return { pendingMemories, online, syncing, syncStatus, syncQueue, lastSyncedAt };
}
