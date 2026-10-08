import { useCallback, useMemo, useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { getMemories } from '../../api/memories';
import type { MemoryKind } from '../../types';

export function useSpaceMemories(spaceId: string, kind?: MemoryKind) {
  const [movedIds, setMovedIds] = useState<Set<string>>(new Set());
  const query = useInfiniteQuery({
    queryKey: ['space', spaceId, 'memories', kind],
    initialPageParam: null,
    queryFn: ({ pageParam, signal }: { pageParam: string | null; signal: AbortSignal }) => getMemories({ spaceId, kind, limit: 100, cursor: pageParam ?? undefined }, signal),
    getNextPageParam: (page) => page.nextCursor,
  });
  const memories = useMemo(() => {
    const records = new Map((query.data?.pages ?? []).flatMap((page) => page.memories).map((memory) => [memory.id, memory]));
    return [...records.values()].filter((memory) => !movedIds.has(memory.id));
  }, [query.data, movedIds]);
  const hideMoved = useCallback((ids: Set<string>) => setMovedIds((current) => new Set([...current, ...ids])), []);
  const { refetch, fetchNextPage, hasNextPage, isFetching } = query;
  const load = useCallback(async () => { await refetch(); }, [refetch]);
  const loadMore = useCallback(async () => { if (hasNextPage && !isFetching) await fetchNextPage({ cancelRefetch: false }); }, [fetchNextPage, hasNextPage, isFetching]);
  return {
    memories, hideMoved, load, loadMore, hasMore: query.hasNextPage,
    loading: query.isPending, refreshing: query.isRefetching,
    loadingMore: query.isFetchingNextPage,
    error: query.isFetchNextPageError ? null : query.error?.message ?? null,
    loadMoreError: query.isFetchNextPageError ? query.error?.message ?? null : null,
  };
}
