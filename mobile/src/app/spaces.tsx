import { RefreshControl, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useWorkspaceActions, useWorkspaceData } from '../providers/workspace-provider';
import { ScreenFrame, ScreenHeader } from '../components';
import { useGoBack } from '../hooks/use-go-back';
import { SpacesScreen } from '../features/spaces/spaces-screen';
import { useTheme } from '../providers/theme-provider';
import { layout, spacing } from '../theme';

export default function SpacesRoute() {
  const { colors } = useTheme();
  const router = useRouter();
  const goBack = useGoBack();
  const { spaces, defaultCaptureSpaceId, loading, refreshing } = useWorkspaceData();
  const { loadWorkspace } = useWorkspaceActions();
  const selectSpace = (id: string | null) => {
    if (id) router.push({ pathname: '/space/[id]', params: { id } });
    else router.replace('/');
  };
  return <ScreenFrame header={<ScreenHeader title="Spaces" subtitle="Projects, interests, and plans. A memory can live in more than one." onBack={goBack} />}>
    <ScrollView style={{ flex: 1, backgroundColor: colors.background }} contentContainerStyle={{ paddingHorizontal: layout.gutter, paddingBottom: spacing.xxl }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void loadWorkspace()} tintColor={colors.blueDeep} colors={[colors.blueDeep]} />}>
      <SpacesScreen spaces={spaces} defaultCaptureSpaceId={defaultCaptureSpaceId} loading={loading} onSelectSpace={selectSpace} onCreateSpace={() => router.push('/space/new')} />
    </ScrollView>
  </ScreenFrame>;
}
