import { RefreshControl, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { getPlan } from '../../api/plans';
import { useWorkspaceActions, useWorkspaceData } from '../../providers/workspace-provider';
import { useTrovePreferences } from '../../providers/preferences-provider';
import { useTheme } from '../../providers/theme-provider';
import { useGoBack } from '../../hooks/use-go-back';
import { ProfileScreen } from '../../features/profile/profile-screen';
import { ScreenFrame, ScreenHeader } from '../../components';
import { layout, spacing } from '../../theme';

export default function ProfileRoute() {
  const goBack = useGoBack();
  const router = useRouter();
  const { colors, theme, themeLoaded, changeTheme } = useTheme();
  const { syncStatus, pendingMemories, syncing, lastSyncedAt, refreshing } = useWorkspaceData();
  const { loadWorkspace, syncQueue } = useWorkspaceActions();
  const { backgroundSync, localSettingsLoaded, changeBackgroundSync, exportMemories } = useTrovePreferences();
  const planQuery = useQuery({ queryKey: ['plan'], queryFn: getPlan, staleTime: 30_000 });
  return <ScreenFrame header={<ScreenHeader title="Profile" onBack={goBack} />}><ScrollView style={{ flex: 1, backgroundColor: colors.background }} contentContainerStyle={{ paddingHorizontal: layout.gutter, paddingBottom: layout.navBar + spacing.xxxxl }} refreshControl={<RefreshControl refreshing={refreshing || planQuery.isRefetching} onRefresh={() => void Promise.all([loadWorkspace(), planQuery.refetch()])} tintColor={colors.blueDeep} colors={[colors.blueDeep]} />}>
    <ProfileScreen backgroundSync={backgroundSync} localSettingsLoaded={localSettingsLoaded} theme={theme} themeLoaded={themeLoaded} syncStatus={syncStatus} pendingCount={pendingMemories.length} syncing={syncing} lastSyncedAt={lastSyncedAt} loading={refreshing} plan={planQuery.data?.plan ?? null} planLoading={planQuery.isPending} planError={planQuery.error?.message ?? null} onToggleSync={changeBackgroundSync} onChangeTheme={changeTheme} onSyncNow={() => void syncQueue(true)} onOpenCloud={() => router.push('/cloud')} onExport={() => void exportMemories()} onOpenAccount={() => router.push('/account')} />
  </ScrollView></ScreenFrame>;
}
