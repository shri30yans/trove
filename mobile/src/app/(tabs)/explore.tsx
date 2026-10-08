import { RefreshControl, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useWorkspaceActions, useWorkspaceData } from '../../providers/workspace-provider';
import { useTroveSearchActions } from '../../providers/search-provider';
import { useMemoryDetailsActions } from '../../providers/memory-details-provider';
import { TroveExploreScreen } from '../../features/explore/trove-explore-screen';
import { useTheme } from '../../providers/theme-provider';
import { ScreenFrame, ScreenHeader } from '../../components';
import { layout, spacing } from '../../theme';

export default function ExploreRoute() {
  const { colors } = useTheme();
  const router = useRouter();
  const { spaces, exploreData, updates, displayMemories, loading, refreshing } = useWorkspaceData();
  const { loadWorkspace } = useWorkspaceActions();
  const { openSearch } = useTroveSearchActions();
  const { openMemory } = useMemoryDetailsActions();
  return <ScreenFrame header={<ScreenHeader title="Explore" />}><ScrollView style={{ flex: 1, backgroundColor: colors.background }} contentContainerStyle={{ paddingHorizontal: layout.gutter, paddingBottom: layout.navBar + spacing.xxxxl }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void loadWorkspace()} tintColor={colors.blueDeep} colors={[colors.blueDeep]} />}>
    <TroveExploreScreen
      memories={displayMemories}
      spaces={spaces}
      data={exploreData}
      updates={updates}
      loading={loading}
      onOpenSpaces={() => router.push('/spaces')}
      onOpenSpace={(id) => router.push({ pathname: '/space/[id]', params: { id } })}
      onCreateSpace={() => router.push('/space/new')}
      onOpenMonth={(month, count) => router.push({ pathname: '/month', params: { month, count: String(count) } })}
      onOpenMemory={(memory) => void openMemory(memory)}
      onSearch={(query, kind) => openSearch(query, kind)}
      onCreateMemory={() => router.push('/capture')}
    />
  </ScrollView></ScreenFrame>;
}
