import { useWorkspaceActions, useWorkspaceData } from '../../providers/workspace-provider';
import { useTroveSearchActions, useTroveSearchState } from '../../providers/search-provider';
import { useMemoryDetailsActions } from '../../providers/memory-details-provider';
import { useGoBack } from '../../hooks/use-go-back';
import { SearchScreen } from '../../features/search/search-screen';

export default function SearchRoute() {
  const goBack = useGoBack();
  const { searchQuery, searchKind, searchSpaceId, searchResults, searchLoading, searchError, searchRange: range } = useTroveSearchState();
  const { setSearchQuery, setSearchSpaceId, setSearchKind, setSearchRange, retrySearch } = useTroveSearchActions();
  const { refreshing, spaces } = useWorkspaceData();
  const { loadWorkspace } = useWorkspaceActions();
  const { openMemory } = useMemoryDetailsActions();
  return <SearchScreen error={searchError} onRetry={retrySearch} query={searchQuery} periodLabel={range?.label} queryKind={searchKind} onQueryChange={setSearchQuery} onKindChange={setSearchKind} onRangeChange={setSearchRange} results={searchResults} loading={searchLoading} refreshing={refreshing} spaces={spaces} spaceId={searchSpaceId} onSpaceChange={setSearchSpaceId} onRefresh={() => void loadWorkspace()} onOpenMemory={(memory) => void openMemory(memory)} onBack={goBack} />;
}
