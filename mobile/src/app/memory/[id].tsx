import { useEffect } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { MemoryDetailSheet } from '../../features/memories/memory-detail-sheet';
import { useWorkspaceData } from '../../providers/workspace-provider';
import { useTrovePreferences } from '../../providers/preferences-provider';
import { useMemoryDetailsActions, useMemoryDetailsState } from '../../providers/memory-details-provider';
import { useTroveSearchActions } from '../../providers/search-provider';
import { embeddingState } from '../../domain/embedding-state';

export default function MemoryRoute() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { detailMemory, related, detailLoading, detailError, feedbackError, feedbackPendingId } = useMemoryDetailsState();
  const { spaces } = useWorkspaceData();
  const { preferences, preferencesError } = useTrovePreferences();
  const { sendFeedback, openMemory, loadMemoryDetails, toggleMemorySpace, saveMemoryNote, deleteMemoryAction, closeDetail } = useMemoryDetailsActions();
  const { retrySearch } = useTroveSearchActions();
  useEffect(() => {
    if (!id) return;
    if (detailMemory?.replacesLocalId === id) {
      router.replace({ pathname: '/memory/[id]', params: { id: detailMemory.id } });
      return;
    }
    if (detailMemory?.id !== id) void loadMemoryDetails(id);
  }, [id, detailMemory?.id, detailMemory?.replacesLocalId, loadMemoryDetails, router]);
  return <MemoryDetailSheet memory={detailMemory} related={related} spaces={spaces} loading={detailLoading} error={detailError} feedbackError={feedbackError} feedbackPendingId={feedbackPendingId} embeddingState={embeddingState(preferences, preferencesError)} onClose={closeDetail} onOpenMemory={(memory) => void openMemory(memory)} onToggleSpace={(memory, spaceId) => void toggleMemorySpace(memory, spaceId)} onCreateSpace={() => router.push('/space/new')} onSaveNote={saveMemoryNote} onDelete={async (memory) => { await deleteMemoryAction(memory); retrySearch(); }} onRelatedFeedback={sendFeedback} />;
}
