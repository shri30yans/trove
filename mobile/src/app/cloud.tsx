import { RefreshControl, ScrollView } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getProcessingSummary } from '../api/memories';
import { useWorkspaceActions, useWorkspaceData } from '../providers/workspace-provider';
import { useTrovePreferences } from '../providers/preferences-provider';
import { embeddingState } from '../domain/embedding-state';
import { ScreenFrame, ScreenHeader } from '../components';
import { useGoBack } from '../hooks/use-go-back';
import { CloudScreen } from '../features/cloud/cloud-screen';
import { useTheme } from '../providers/theme-provider';
import { layout, spacing } from '../theme';

export default function CloudRoute() {
  const { colors } = useTheme();
  const goBack = useGoBack();
  const { syncStatus, pendingMemories, syncing, lastSyncedAt } = useWorkspaceData();
  const { syncQueue } = useWorkspaceActions();
  const { preferences, preferencesError, reloadPreferences } = useTrovePreferences();
  const processingQuery = useQuery({ queryKey: ['processing'], queryFn: () => getProcessingSummary() });
  const refetchProcessing = processingQuery.refetch;
  useFocusEffect(useCallback(() => { void refetchProcessing(); }, [refetchProcessing]));
  return <ScreenFrame header={<ScreenHeader title="Cloud" subtitle="What left this device, and what the server did with it." onBack={goBack} />}>
    <ScrollView style={{ flex: 1, backgroundColor: colors.background }} contentContainerStyle={{ paddingHorizontal: layout.gutter, paddingBottom: spacing.xxl }} refreshControl={<RefreshControl refreshing={processingQuery.isRefetching} onRefresh={() => void Promise.all([reloadPreferences(), processingQuery.refetch()])} tintColor={colors.blueDeep} colors={[colors.blueDeep]} />}>
      <CloudScreen
        syncStatus={syncStatus}
        pendingCount={pendingMemories.length}
        syncing={syncing}
        lastSyncedAt={lastSyncedAt}
        onSyncNow={() => void syncQueue(true)}
        processingLoading={processingQuery.isPending}
        processingError={processingQuery.error?.message ?? null}
        processingCounts={processingQuery.data?.processing ?? null}
        onRetryProcessing={() => void processingQuery.refetch()}
        embeddingState={embeddingState(preferences, preferencesError)}
        onRetryEmbeddings={() => void reloadPreferences()}
      />
    </ScrollView>
  </ScreenFrame>;
}
