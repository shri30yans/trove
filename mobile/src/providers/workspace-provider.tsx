import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Alert } from 'react-native';
import { useStoredPreference } from '../hooks/use-stored-preference';
import { defaultSpacePreference } from '../storage/local-preferences';
import type { SyncStatus } from '../features/sync/sync-status';
import { useMemoryLibrary } from '../features/workspace/use-memory-library';
import { queueOfflineCapture } from '../features/sync/save-capture';
import { useWorkspaceOverview } from '../features/workspace/use-workspace-overview';
import { useCaptureDelivery } from '../features/sync/use-capture-delivery';
import { useShareIntentCapture } from '../features/capture/use-share-intent-capture';
import { useTroveToastContext } from './toast-provider';
import { useTrovePreferences } from './preferences-provider';
import type { ExploreData, Memory, MemoryCapture, ResurfacingUpdate, Space, WrittenSpace } from '../types';


export type WorkspaceData = {
  memories: Memory[];
  displayMemories: Memory[];
  pendingMemories: Memory[];
  spaces: Space[];
  defaultCaptureSpaceId: string | null;
  hasMoreMemories: boolean;
  loadingMoreMemories: boolean;
  exploreData: ExploreData | null;
  updates: ResurfacingUpdate[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  online: boolean;
  syncing: boolean;
  syncStatus: SyncStatus;
  lastSyncedAt: string | null;
};

export type WorkspaceActions = {
  setDefaultCaptureSpaceId: (id: string | null) => void;
  addSpace: (space: WrittenSpace) => void;
  loadWorkspace: (quiet?: boolean) => Promise<void>;
  loadMoreMemories: () => Promise<void>;
  saveCapture: (capture: MemoryCapture) => Promise<boolean>;
  syncQueue: (notify?: boolean) => Promise<void>;
  upsertMemory: (memory: Memory) => void;
  removeMemory: (id: string) => void;
};

const WorkspaceDataContext = createContext<WorkspaceData | null>(null);
const WorkspaceActionsContext = createContext<WorkspaceActions | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { showToast } = useTroveToastContext();
  const { backgroundSync, localSettingsLoaded, reloadPreferences } = useTrovePreferences();
  const { value: defaultCaptureSpaceId, error: defaultSpaceError, setValue: setDefaultCaptureSpaceId } = useStoredPreference(defaultSpacePreference, null);
  const [refreshing, setRefreshing] = useState(false);
  const library = useMemoryLibrary();
  const { memories, upsertMemory, loadMoreMemories, hasMoreMemories, loadingMoreMemories, refresh: refreshMemories, removeMemory: removeLibraryMemory } = library;
  const overview = useWorkspaceOverview();
  const { spaces, exploreData, addSpace, updates, refresh, hideMemory } = overview;

  const reconcileDeliveredCapture = useCallback((localId: string, memory: Memory) => {
    upsertMemory({ ...memory, replacesLocalId: localId });
  }, [upsertMemory]);
  const { pendingMemories, online, syncing, syncStatus, syncQueue, lastSyncedAt } = useCaptureDelivery({
    backgroundSync, localSettingsLoaded, showToast,
    onSynced: reconcileDeliveredCapture, onDelivered: overview.refreshSpaces,
  });

  useEffect(() => {
    if (defaultSpaceError) showToast(defaultSpaceError);
  }, [defaultSpaceError, showToast]);

  const loadWorkspace = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      await Promise.all([refresh(), refreshMemories(), reloadPreferences()]);
    } finally {
      if (!quiet) setRefreshing(false);
    }
  }, [refreshMemories, refresh, reloadPreferences]);

  const saveCapture = useCallback(async (capture: MemoryCapture) => {
    const defaultSpaceIsValid = defaultCaptureSpaceId && spaces.some((space) => space.id === defaultCaptureSpaceId);
    const routedCapture = capture.spaceIds !== undefined || !defaultSpaceIsValid
      ? capture
      : { ...capture, spaceIds: [defaultCaptureSpaceId] };

    try {
      await queueOfflineCapture(routedCapture);
      showToast(!backgroundSync ? 'Saved on this device. Automatic sync is off.' : 'Saved on this device.');
      return true;
    } catch (saveError) {
      Alert.alert('Could not save this', saveError instanceof Error ? saveError.message : 'Try again in a moment.');
      return false;
    }
  }, [backgroundSync, defaultCaptureSpaceId, showToast, spaces]);

  useShareIntentCapture(saveCapture, showToast);

  const removeMemory = useCallback((id: string) => {
    removeLibraryMemory(id);
    hideMemory(id);
  }, [hideMemory, removeLibraryMemory]);

  const data = useMemo<WorkspaceData>(() => ({
    memories,
    displayMemories: [...pendingMemories, ...memories],
    pendingMemories,
    spaces,
    defaultCaptureSpaceId,
    hasMoreMemories,
    loadingMoreMemories,
    exploreData,
    updates,
    loading: overview.loading || library.loading,
    refreshing,
    error: library.error ?? overview.error,
    online, syncing, syncStatus, lastSyncedAt,
  }), [memories, pendingMemories, spaces, defaultCaptureSpaceId, hasMoreMemories, loadingMoreMemories, exploreData, updates, overview.loading, overview.error, library.loading, library.error, refreshing, online, syncing, syncStatus, lastSyncedAt]);

  const actions = useMemo<WorkspaceActions>(() => ({
    setDefaultCaptureSpaceId, addSpace, loadWorkspace, loadMoreMemories, saveCapture, syncQueue, upsertMemory, removeMemory,
  }), [addSpace, loadWorkspace, loadMoreMemories, saveCapture, setDefaultCaptureSpaceId, syncQueue, upsertMemory, removeMemory]);

  return <WorkspaceDataContext.Provider value={data}>
    <WorkspaceActionsContext.Provider value={actions}>{children}</WorkspaceActionsContext.Provider>
  </WorkspaceDataContext.Provider>;
}

export function useWorkspaceData() {
  const value = useContext(WorkspaceDataContext);
  if (!value) throw new Error('useWorkspaceData must be used inside WorkspaceProvider.');
  return value;
}

export function useWorkspaceActions() {
  const value = useContext(WorkspaceActionsContext);
  if (!value) throw new Error('useWorkspaceActions must be used inside WorkspaceProvider.');
  return value;
}
