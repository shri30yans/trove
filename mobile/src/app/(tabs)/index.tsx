import { useRouter } from 'expo-router';
import { useWorkspaceActions, useWorkspaceData } from '../../providers/workspace-provider';
import { useTroveSearchActions } from '../../providers/search-provider';
import { useMemoryDetailsActions } from '../../providers/memory-details-provider';
import { HomeScreen } from '../../features/home/home-screen';
import { ScreenFrame } from '../../components';

export default function HomeRoute() {
  const router = useRouter();
  const { displayMemories, spaces, updates, hasMoreMemories, loadingMoreMemories, loading, error, refreshing } = useWorkspaceData();
  const { loadMoreMemories, loadWorkspace } = useWorkspaceActions();
  const { openSearch } = useTroveSearchActions();
  const { openMemory } = useMemoryDetailsActions();
  return <ScreenFrame><HomeScreen memories={displayMemories} spaces={spaces} updates={updates} hasMoreMemories={hasMoreMemories} loadingMoreMemories={loadingMoreMemories} loading={loading} refreshing={refreshing} error={error} onOpenProfile={() => router.push('/profile')} onOpenMemory={(memory) => void openMemory(memory)} onLoadMore={() => void loadMoreMemories()} onSearch={openSearch} onOpenSpaces={() => router.push('/spaces')} onOpenSpace={(id) => router.push({ pathname: '/space/[id]', params: { id } })} onCreateSpace={() => router.push('/space/new')} onRefresh={() => void loadWorkspace()} /></ScreenFrame>;
}
