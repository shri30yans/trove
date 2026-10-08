import { useCallback, useMemo, useRef, useState } from 'react';
import { useInfiniteQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query';
import { memorySearchKey } from '../search/search-query';
import { getMemories } from '../../api/memories';
import type { Memory } from '../../types';
import { projectMemoryLibrary, type ConfirmedMemory, type MemoryPage } from './memory-library';

export function useMemoryLibrary() {
  const client = useQueryClient();
  const cachedPages = client.getQueryData<InfiniteData<MemoryPage>>(['workspace', 'memories'])?.pages ?? [];
  const revision = useRef(Math.max(0, ...cachedPages.map((page) => page.startedRevision)));
  const [confirmed, setConfirmed] = useState<ConfirmedMemory[]>([]);
  const [deleted, setDeleted] = useState<Set<string>>(new Set());
  const query = useInfiniteQuery({
    queryKey: ['workspace', 'memories'],
    initialPageParam: null,
    queryFn: async ({ pageParam, signal }: { pageParam: string | null; signal: AbortSignal }) => {
      const startedRevision = revision.current;
      const page = await getMemories({ limit: 50, cursor: pageParam ?? undefined }, signal);
      return { ...page, startedRevision };
    },
    getNextPageParam: (page) => page.nextCursor,
  });
  const memories = useMemo(() => projectMemoryLibrary(query.data?.pages ?? [], confirmed, deleted), [query.data, confirmed, deleted]);
  const upsertMemory = useCallback((memory: Memory) => {
    void client.invalidateQueries({ queryKey: memorySearchKey });
    const nextRevision = ++revision.current;
    setConfirmed((current) => [{ memory: {
      ...memory, replacesLocalId: memory.replacesLocalId ?? current.find((entry) => entry.memory.id === memory.id)?.memory.replacesLocalId,
    }, revision: nextRevision }, ...current.filter((entry) => entry.memory.id !== memory.id)]);
  }, [client]);
  const removeMemory = useCallback((id: string) => {
    client.removeQueries({ queryKey: memorySearchKey });
    setDeleted((current) => new Set([...current, id]));
    setConfirmed((current) => current.filter((entry) => entry.memory.id !== id));
  }, [client]);
  const { refetch, fetchNextPage, isFetching, hasNextPage } = query;
  const refresh = useCallback(async () => { await refetch(); }, [refetch]);
  const loadMoreMemories = useCallback(async () => {
    if (hasNextPage && !isFetching) await fetchNextPage({ cancelRefetch: false });
  }, [fetchNextPage, hasNextPage, isFetching]);
  return {
    memories, upsertMemory, removeMemory, refresh, loadMoreMemories,
    loading: query.isPending,
    loadingMoreMemories: query.isFetchingNextPage,
    hasMoreMemories: query.hasNextPage,
    error: query.error?.message ?? null,
  };
}
