import { useCallback, useState } from 'react';
import { Alert } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter, useSegments } from 'expo-router';
import { deleteMemory, getMemory, patchMemory } from '../../api/memories';
import { getRelatedMemories } from '../../api/search';
import { useRelatedFeedback } from './use-related-feedback';
import type { Memory } from '../../types';

type UseMemoryDetailsOptions = {
  memories: Memory[];
  pendingMemories: Memory[];
  upsertMemory: (memory: Memory) => void;
  removeMemory: (id: string) => void;
  loadWorkspace: (quiet?: boolean) => Promise<void>;
  showToast: (message: string) => void;
};

export function useMemoryDetails({ memories, pendingMemories, upsertMemory, removeMemory, loadWorkspace, showToast }: UseMemoryDetailsOptions) {
  const router = useRouter();
  const segments: string[] = useSegments();
  const client = useQueryClient();
  const [selection, setSelection] = useState<{ id: string; preview: Memory | null } | null>(null);
  const pending = selection ? pendingMemories.find((item) => item.id === selection.id) : undefined;
  const acknowledged = selection ? memories.find((item) => item.replacesLocalId === selection.id) : undefined;
  const id = acknowledged?.id ?? selection?.id;
  const feedback = useRelatedFeedback(id);
  const local = pending ?? (selection?.preview?.localPending && !acknowledged ? selection.preview : null);
  const detailQuery = useQuery({
    queryKey: ['memory', id], enabled: !!id && !local,
    queryFn: ({ signal }) => {
      if (!id) throw new Error('Select a memory first.');
      return getMemory(id, signal);
    },
  });
  const relatedQuery = useQuery({
    queryKey: ['memory', id, 'related'], enabled: !!id && !local,
    queryFn: ({ signal }) => {
      if (!id) throw new Error('Select a memory first.');
      return getRelatedMemories(id, signal);
    },
  });
  const listed = memories.find((memory) => memory.id === id);
  const remote = detailQuery.data?.memory;
  const detailMemory: Memory | null = local ?? (remote
    ? { ...remote, replacesLocalId: acknowledged?.replacesLocalId ?? listed?.replacesLocalId }
    : detailQuery.isError ? null : acknowledged ?? listed ?? selection?.preview ?? null);
  const related = relatedQuery.data?.memories ?? [];
  const detailLoading = !!selection && !local && detailQuery.isPending && !detailMemory;
  const detailError = detailQuery.error?.message ?? relatedQuery.error?.message ?? null;
  const loadMemoryDetails = useCallback(async (id: string) => {
    setSelection((current) => current?.id === id ? current : { id, preview: null });
  }, []);
  const navigateToMemory = useCallback((id: string) => {
    const href = { pathname: '/memory/[id]' as const, params: { id } };
    if (segments.includes('memory')) router.replace(href);
    else router.push(href);
  }, [router, segments]);
  const openMemory = useCallback(async (memory: Memory) => {
    setSelection({ id: memory.id, preview: memory });
    navigateToMemory(memory.id);
  }, [navigateToMemory]);
  const confirmMemory = useCallback(async (memory: Memory) => {
    await client.cancelQueries({ queryKey: ['memory', memory.id], exact: true });
    client.setQueryData(['memory', memory.id], { memory });
    upsertMemory(memory);
  }, [client, upsertMemory]);

  const toggleMemorySpace = useCallback(async (memory: Memory, spaceId: string) => {
    if (memory.localPending) { showToast('Spaces are available after this save syncs.'); return; }
    const current = memory.spaces || [];
    const ids = current.some((space) => space.id === spaceId)
      ? current.filter((space) => space.id !== spaceId).map((space) => space.id)
      : [...current.map((space) => space.id), spaceId];
    try {
      const result = await patchMemory(memory.id, { spaceIds: ids });
      await confirmMemory(result.memory);
    } catch (spaceError) {
      Alert.alert('Space could not be updated', spaceError instanceof Error ? spaceError.message : 'Try again in a moment.');
    }
  }, [confirmMemory, showToast]);

  const saveMemoryNote = useCallback(async (memory: Memory, note: string) => {
    if (memory.localPending) { showToast('Notes are available after this save syncs.'); return false; }
    try {
      const result = await patchMemory(memory.id, { userNote: memory.kind === 'text' ? note.trim() : note.trim() || null });
      await confirmMemory(result.memory);
      showToast('Note updated');
      return true;
    } catch (noteError) {
      Alert.alert('Note could not be saved', noteError instanceof Error ? noteError.message : 'Try again in a moment.');
      return false;
    }
  }, [confirmMemory, showToast]);

  const deleteMemoryAction = useCallback(async (memory: Memory) => {
    if (memory.localPending) throw new Error('Wait for this save to sync before deleting it.');
    await deleteMemory(memory.id);
    await client.cancelQueries({ queryKey: ['memory', memory.id] });
    client.removeQueries({ queryKey: ['memory', memory.id] });
    removeMemory(memory.id);
    setSelection(null);
    router.back();
    showToast('Memory deleted');
    void loadWorkspace(true).catch(() => showToast('Memory deleted. Refresh your library to update its counts.'));
  }, [client, removeMemory, loadWorkspace, router, showToast]);

  const closeDetail = useCallback(() => {
    setSelection(null);
    router.back();
  }, [router]);

  return { detailMemory, related, detailLoading, detailError, feedbackError: feedback.error, feedbackPendingId: feedback.pendingId, sendFeedback: feedback.submit, openMemory, loadMemoryDetails, toggleMemorySpace, saveMemoryNote, deleteMemoryAction, closeDetail };
}
