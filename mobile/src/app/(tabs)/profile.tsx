import { Alert, RefreshControl, ScrollView } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPlan } from '../../api/plans';
import { useWorkspaceActions, useWorkspaceData } from '../../providers/workspace-provider';
import { useTrovePreferences } from '../../providers/preferences-provider';
import { useTheme } from '../../providers/theme-provider';
import { useGoBack } from '../../hooks/use-go-back';
import { ProfileScreen } from '../../features/profile/profile-screen';
import { useAuth } from '../../providers/auth-provider';
import { ScreenFrame, ScreenHeader } from '../../components';
import { layout, spacing } from '../../theme';

export default function ProfileRoute() {
  const goBack = useGoBack();
  const router = useRouter();
  const { signOut, deleteAccount } = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const { colors, theme, themeLoaded, changeTheme } = useTheme();
  const { syncStatus, pendingMemories, syncing, lastSyncedAt, refreshing } = useWorkspaceData();
  const { loadWorkspace, syncQueue } = useWorkspaceActions();
  const { backgroundSync, localSettingsLoaded, changeBackgroundSync, exportMemories } = useTrovePreferences();
  const planQuery = useQuery({ queryKey: ['plan'], queryFn: getPlan });
  const refetchPlan = planQuery.refetch;
  useFocusEffect(useCallback(() => { void refetchPlan(); }, [refetchPlan]));
  function scheduleAccountDeletion() {
    Alert.alert('Schedule account deletion?', 'Your account and cloud memories will be deleted after a 7-day recovery period. You can cancel before the deadline to keep them.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete account', style: 'destructive', onPress: () => {
        setDeletingAccount(true);
        void deleteAccount().catch((error: unknown) => Alert.alert('Could not schedule deletion', error instanceof Error ? error.message : 'Try again shortly.')).finally(() => setDeletingAccount(false));
      } },
    ]);
  }
  return <ScreenFrame header={<ScreenHeader title="Profile" onBack={goBack} />}><ScrollView style={{ flex: 1, backgroundColor: colors.background }} contentContainerStyle={{ paddingHorizontal: layout.gutter, paddingBottom: layout.navBar + spacing.xxxxl }} refreshControl={<RefreshControl refreshing={refreshing || planQuery.isRefetching} onRefresh={() => void Promise.all([loadWorkspace(), planQuery.refetch()])} tintColor={colors.blueDeep} colors={[colors.blueDeep]} />}>
    <ProfileScreen backgroundSync={backgroundSync} localSettingsLoaded={localSettingsLoaded} theme={theme} themeLoaded={themeLoaded} syncStatus={syncStatus} pendingCount={pendingMemories.length} syncing={syncing} lastSyncedAt={lastSyncedAt} loading={refreshing} plan={planQuery.data?.plan ?? null} planLoading={planQuery.isPending} planError={planQuery.error?.message ?? null} onToggleSync={changeBackgroundSync} onChangeTheme={changeTheme} onSyncNow={() => void syncQueue(true)} onOpenCloud={() => router.push('/cloud')} onExport={() => void exportMemories()} showSignOut signingOut={signingOut} deletingAccount={deletingAccount} onSignOut={() => { setSigningOut(true); void signOut().catch((error: unknown) => Alert.alert('Could not sign out', error instanceof Error ? error.message : 'Try again.')).finally(() => setSigningOut(false)); }} onDeleteAccount={scheduleAccountDeletion} />
  </ScrollView></ScreenFrame>;
}
