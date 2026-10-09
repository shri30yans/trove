import { keepPreviousData, queryOptions } from '@tanstack/react-query';
import { getMemories } from '../../api/memories';
import { searchMemories } from '../../api/search';
import type { MemoryFilters } from '../../api/memory-filters';

export const memorySearchKey = ['memory-search'] as const;

/** A repeated filter within this window is served from cache; the user changed their mind often
 * enough after it that a fresh read is worth the round trip. */
const SEARCH_RESULT_FRESH_MS = 30_000;

export function memorySearchOptions(filters: MemoryFilters & { query: string; mode?: 'hybrid' | 'raw'; tag?: string }) {
  return queryOptions({
    staleTime: SEARCH_RESULT_FRESH_MS,
    placeholderData: keepPreviousData,
    queryKey: [...memorySearchKey, filters],
    queryFn: async ({ signal }) => {
      if (filters.query || filters.tag) return searchMemories(filters, signal);
      const result = await getMemories({ ...filters, limit: 50 }, signal);
      return { memories: result.memories, semanticSearch: false };
    },
  });
}
