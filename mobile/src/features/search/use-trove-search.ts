import { useCallback, useState } from 'react';
import { useRouter, useSegments } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useDebounce } from 'use-debounce';
import type { MemoryKind } from '../../types';
import { memorySearchKey, memorySearchOptions } from './search-query';

type SearchKind = MemoryKind | 'all';
export type SearchMode = 'hybrid' | 'raw';
export type SearchRange = { after: string; before: string; label: string };

function searchKind(value: string): SearchKind {
  switch (value) {
    case 'all': case 'link': case 'image': case 'text': case 'audio': case 'video': case 'file': return value;
    default: throw new Error(`Unsupported memory type: ${value}`);
  }
}

export function useTroveSearch() {
  const router = useRouter();
  const segments = useSegments();
  const client = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [kind, setKind] = useState<SearchKind>('all');
  const [searchRange, setSearchRange] = useState<SearchRange | null>(null);
  const [searchSpaceId, setSearchSpaceId] = useState<string | null>(null);
  const [searchMode, setSearchMode] = useState<SearchMode>('hybrid');
  const [searchTag, setSearchTag] = useState<string | null>(null);
  const [query] = useDebounce(searchQuery.trim(), 180);
  const typing = query !== searchQuery.trim();
  const hasSearch = !!(searchQuery.trim() || kind !== 'all' || searchRange || searchSpaceId || searchTag);
  const result = useQuery({
    ...memorySearchOptions({ query, kind, after: searchRange?.after, before: searchRange?.before, spaceId: searchSpaceId ?? undefined, mode: searchMode, tag: searchTag ?? undefined }),
    enabled: segments.some((segment) => segment === 'search') && hasSearch && !typing,
  });
  const retrySearch = useCallback(() => {
    void client.invalidateQueries({ queryKey: memorySearchKey });
  }, [client]);
  const setSearchKind = useCallback((value: string) => setKind(searchKind(value)), []);
  const openSearch = useCallback((query: string, kind = 'all', range?: SearchRange, spaceId?: string, tag?: string) => {
    setSearchQuery(query);
    setKind(searchKind(kind));
    setSearchRange(range ?? null);
    setSearchSpaceId(spaceId ?? null);
    setSearchTag(tag ?? null);
    router.navigate('/search');
  }, [router]);
  return {
    searchQuery, searchKind: kind, searchRange, searchSpaceId, searchMode, searchTag,
    searchResults: hasSearch ? result.data?.memories ?? [] : [],
    searchLoading: hasSearch && (typing || result.isPending || result.isFetching),
    semanticSearch: hasSearch && !typing && result.data?.semanticSearch === true,
    searchError: hasSearch && !typing && result.error ? result.error.message : null,
    setSearchQuery, setSearchKind, setSearchRange, setSearchSpaceId, setSearchMode, setSearchTag, retrySearch, openSearch,
  };
}
