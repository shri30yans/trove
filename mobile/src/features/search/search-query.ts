import { keepPreviousData, queryOptions } from '@tanstack/react-query';
import { getMemories } from '../../api/memories';
import { searchMemories } from '../../api/search';
import type { MemoryFilters } from '../../api/memory-filters';

export const memorySearchKey = ['memory-search'] as const;

export function memorySearchOptions(filters: MemoryFilters & { query: string }) {
  return queryOptions({
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    queryKey: [...memorySearchKey, filters],
    queryFn: async ({ signal }) => {
      if (filters.query) return searchMemories(filters, signal);
      const result = await getMemories({ ...filters, limit: 50 }, signal);
      return { memories: result.memories, semanticSearch: false };
    },
  });
}
