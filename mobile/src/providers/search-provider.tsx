import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useTroveSearch, type SearchMode, type SearchRange } from '../features/search/use-trove-search';
import type { Memory } from '../types';

type SearchState = {
  searchQuery: string;
  searchKind: string;
  searchRange: SearchRange | null;
  searchSpaceId: string | null;
  searchMode: SearchMode;
  searchTag: string | null;
  searchResults: Memory[];
  searchLoading: boolean;
  semanticSearch: boolean;
  searchError: string | null;
};

type SearchActions = {
  setSearchQuery: (query: string) => void;
  setSearchKind: (kind: string) => void;
  setSearchRange: (range: SearchRange | null) => void;
  setSearchSpaceId: (id: string | null) => void;
  setSearchMode: (mode: SearchMode) => void;
  setSearchTag: (tag: string | null) => void;
  retrySearch: () => void;
  openSearch: (query: string, kind?: string, range?: SearchRange, spaceId?: string, tag?: string) => void;
};

const SearchStateContext = createContext<SearchState | null>(null);
const SearchActionsContext = createContext<SearchActions | null>(null);

export function SearchProvider({ children }: { children: ReactNode }) {
  const search = useTroveSearch();
  const state = useMemo<SearchState>(() => ({
    searchQuery: search.searchQuery,
    searchKind: search.searchKind,
    searchRange: search.searchRange,
    searchSpaceId: search.searchSpaceId,
    searchMode: search.searchMode,
    searchTag: search.searchTag,
    searchResults: search.searchResults,
    searchLoading: search.searchLoading,
    semanticSearch: search.semanticSearch,
    searchError: search.searchError,
  }), [search.searchQuery, search.searchKind, search.searchRange, search.searchSpaceId, search.searchMode, search.searchTag, search.searchResults, search.searchLoading, search.semanticSearch, search.searchError]);
  const actions = useMemo<SearchActions>(() => ({
    setSearchQuery: search.setSearchQuery,
    setSearchKind: search.setSearchKind,
    setSearchRange: search.setSearchRange,
    setSearchSpaceId: search.setSearchSpaceId,
    setSearchMode: search.setSearchMode,
    setSearchTag: search.setSearchTag,
    retrySearch: search.retrySearch,
    openSearch: search.openSearch,
  }), [search.setSearchQuery, search.setSearchKind, search.setSearchRange, search.setSearchSpaceId, search.setSearchMode, search.setSearchTag, search.retrySearch, search.openSearch]);

  return <SearchStateContext.Provider value={state}>
    <SearchActionsContext.Provider value={actions}>{children}</SearchActionsContext.Provider>
  </SearchStateContext.Provider>;
}

export function useTroveSearchState() {
  const value = useContext(SearchStateContext);
  if (!value) throw new Error('useTroveSearchState must be used inside SearchProvider.');
  return value;
}

export function useTroveSearchActions() {
  const value = useContext(SearchActionsContext);
  if (!value) throw new Error('useTroveSearchActions must be used inside SearchProvider.');
  return value;
}
