import { useWorkspaceActions, useWorkspaceData } from '../../providers/workspace-provider';
import { useTroveSearchActions, useTroveSearchState } from '../../providers/search-provider';
import { useMemoryDetailsActions } from '../../providers/memory-details-provider';
import { useGoBack } from '../../hooks/use-go-back';
import { SearchScreen } from '../../features/search/search-screen';

export default function SearchRoute() {
  const goBack = useGoBack();
  const { searchQuery, searchKind, searchSpaceId, searchMode, searchTag, searchResults, searchLoading, searchError, searchRange: range } = useTroveSearchState();
  const { setSearchQuery, setSearchSpaceId, setSearchKind, setSearchRange, setSearchMode, setSearchTag, retrySearch } = useTroveSearchActions();
  const { refreshing, spaces } = useWorkspaceData();
  const { loadWorkspace } = useWorkspaceActions();
  const { openMemory } = useMemoryDetailsActions();
  return <SearchScreen error={searchError} onRetry={retrySearch} query={searchQuery} tag={searchTag} onTagChange={setSearchTag} periodLabel={range?.label} queryKind={searchKind} searchMode={searchMode} onSearchModeChange={setSearchMode} onQueryChange={setSearchQuery} onKindChange={setSearchKind} onRangeChange={setSearchRange} results={searchResults} loading={searchLoading} refreshing={refreshing} spaces={spaces} spaceId={searchSpaceId} onSpaceChange={setSearchSpaceId} onRefresh={() => void loadWorkspace()} onOpenMemory={(memory) => void openMemory(memory)} onBack={goBack} />;
}
