import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useMemoryDetails } from '../features/memories/use-memory-details';
import { useTroveToastContext } from './toast-provider';
import { useWorkspaceActions, useWorkspaceData } from './workspace-provider';

const MemoryDetailsStateContext = createContext<Pick<ReturnType<typeof useMemoryDetails>, 'detailMemory' | 'related' | 'detailLoading' | 'detailError' | 'feedbackError' | 'feedbackPendingId'> | null>(null);
const MemoryDetailsActionsContext = createContext<Omit<ReturnType<typeof useMemoryDetails>, 'detailMemory' | 'related' | 'detailLoading' | 'detailError' | 'feedbackError' | 'feedbackPendingId'> | null>(null);

export function MemoryDetailsProvider({ children }: { children: ReactNode }) {
  const { memories, pendingMemories } = useWorkspaceData();
  const { upsertMemory, removeMemory, loadWorkspace } = useWorkspaceActions();
  const { showToast } = useTroveToastContext();
  const details = useMemoryDetails({ memories, pendingMemories, upsertMemory, removeMemory, loadWorkspace, showToast });
  const state = useMemo(() => ({
    detailMemory: details.detailMemory,
    related: details.related,
    detailLoading: details.detailLoading,
    detailError: details.detailError,
    feedbackError: details.feedbackError,
    feedbackPendingId: details.feedbackPendingId,
  }), [details.detailMemory, details.related, details.detailLoading, details.detailError, details.feedbackError, details.feedbackPendingId]);
  const actions = useMemo(() => ({
    sendFeedback: details.sendFeedback,
    openMemory: details.openMemory,
    loadMemoryDetails: details.loadMemoryDetails,
    toggleMemorySpace: details.toggleMemorySpace,
    saveMemoryNote: details.saveMemoryNote,
    saveMemoryTags: details.saveMemoryTags,
    closeDetail: details.closeDetail,
    deleteMemoryAction: details.deleteMemoryAction,
  }), [details.sendFeedback, details.openMemory, details.loadMemoryDetails, details.toggleMemorySpace, details.saveMemoryNote, details.saveMemoryTags, details.deleteMemoryAction, details.closeDetail]);

  return <MemoryDetailsStateContext.Provider value={state}>
    <MemoryDetailsActionsContext.Provider value={actions}>{children}</MemoryDetailsActionsContext.Provider>
  </MemoryDetailsStateContext.Provider>;
}

export function useMemoryDetailsState() {
  const value = useContext(MemoryDetailsStateContext);
  if (!value) throw new Error('useMemoryDetailsState must be used inside MemoryDetailsProvider.');
  return value;
}

export function useMemoryDetailsActions() {
  const value = useContext(MemoryDetailsActionsContext);
  if (!value) throw new Error('useMemoryDetailsActions must be used inside MemoryDetailsProvider.');
  return value;
}
