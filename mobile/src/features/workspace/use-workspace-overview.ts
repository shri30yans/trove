import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getExplore, getUpdates } from '../../api/overview';
import { getSpaces } from '../../api/spaces';
import type { Space } from '../../types';

/** Server reads own request state; confirmed creations survive older list responses. */
export function useWorkspaceOverview() {
  const spacesQuery = useQuery({ queryKey: ['workspace', 'spaces'], queryFn: getSpaces });
  const exploreQuery = useQuery({ queryKey: ['workspace', 'explore'], queryFn: getExplore });
  const updatesQuery = useQuery({ queryKey: ['workspace', 'updates'], queryFn: getUpdates });
  const [deletedMemoryIds, setDeletedMemoryIds] = useState<Set<string>>(new Set());
  const hideMemory = useCallback((id: string) => {
    setDeletedMemoryIds((current) => new Set([...current, id]));
  }, []);
  const [createdSpaces, setCreatedSpaces] = useState<Space[]>([]);
  const spaces = useMemo(() => {
    const listed = spacesQuery.data?.spaces ?? [];
    const ids = new Set(listed.map((space) => space.id));
    return [...listed, ...createdSpaces.filter((space) => !ids.has(space.id))];
  }, [spacesQuery.data, createdSpaces]);
  const addSpace = useCallback((space: Space) => {
    setCreatedSpaces((current) => [...current.filter((item) => item.id !== space.id), space]);
  }, []);
  const { refetch: refetchSpaces } = spacesQuery;
  const { refetch: refetchExplore } = exploreQuery;
  const { refetch: refetchUpdates } = updatesQuery;
  const refreshSpaces = useCallback(() => { void refetchSpaces(); }, [refetchSpaces]);
  const refresh = useCallback(async () => {
    await Promise.all([refetchSpaces(), refetchExplore(), refetchUpdates()]);
  }, [refetchSpaces, refetchExplore, refetchUpdates]);
  const error = spacesQuery.error ?? exploreQuery.error ?? updatesQuery.error;
  return {
    spaces, addSpace, refresh, refreshSpaces, hideMemory,
    exploreData: exploreQuery.data ?? null,
    updates: (updatesQuery.data?.updates ?? []).filter((update) => !deletedMemoryIds.has(update.memory.id)),
    loading: spacesQuery.isPending || exploreQuery.isPending || updatesQuery.isPending,
    error: error?.message ?? null,
  };
}
