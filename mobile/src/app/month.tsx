import { useCallback, useEffect, useMemo, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useMemoryDetailsActions } from '../providers/memory-details-provider';
import { getMemories } from '../api/memories';
import { LoadMoreButton, MemoryRow, ScreenFrame, ScreenHeader } from '../components';
import { useGoBack } from '../hooks/use-go-back';
import { MonthlyOverviewScreen } from '../features/memories/monthly-overview-screen';
import { useTheme, useThemedStyles } from '../providers/theme-provider';
import type { Memory } from '../types';
import { layout, spacing, text, type Palette } from '../theme';

function getMonthStart(value: string | undefined) {
  const candidate = value ? new Date(value) : new Date();
  const date = Number.isNaN(candidate.getTime()) ? new Date() : candidate;
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

export default function MonthRoute() {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const { month, count } = useLocalSearchParams<{ month?: string; count?: string }>();
  const goBack = useGoBack();
  const { openMemory } = useMemoryDetailsActions();
  const monthStart = useMemo(() => getMonthStart(month), [month]);
  const monthDate = monthStart.toISOString();
  const after = monthDate;
  const before = new Date(Date.UTC(monthStart.getUTCFullYear(), monthStart.getUTCMonth() + 1, 1)).toISOString();
  const rangeKey = `${after}:${before}`;
  const totalCount = count && Number.isFinite(Number(count)) ? Number(count) : undefined;
  const [page, setPage] = useState<{ rangeKey: string; memories: Memory[]; nextCursor: string | null; error: string | null }>({ rangeKey: '', memories: [], nextCursor: null, error: null });
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const loading = page.rangeKey !== rangeKey;
  const memories = loading ? [] : page.memories;
  const error = loading ? null : page.error;

  useEffect(() => {
    let active = true;
    getMemories({ after, before, limit: 100 }).then((result) => {
      if (active) setPage({ rangeKey, memories: result.memories, nextCursor: result.nextCursor, error: null });
    }).catch((loadError: unknown) => {
      if (active) setPage({ rangeKey, memories: [], nextCursor: null, error: loadError instanceof Error ? loadError.message : 'Could not load this month.' });
    });
    return () => { active = false; };
  }, [after, before, rangeKey]);

  const load = useCallback(() => {
    setRefreshing(true);
    getMemories({ after, before, limit: 100 }).then((result) => {
      setPage({ rangeKey, memories: result.memories, nextCursor: result.nextCursor, error: null });
    }).catch((loadError: unknown) => {
      setPage({ rangeKey, memories: [], nextCursor: null, error: loadError instanceof Error ? loadError.message : 'Could not load this month.' });
    }).finally(() => setRefreshing(false));
  }, [after, before, rangeKey]);
  const loadMore = useCallback(() => {
    if (!page.nextCursor || page.rangeKey !== rangeKey || loadingMore) return;
    const cursor = page.nextCursor;
    setLoadingMore(true);
    setLoadMoreError(null);
    getMemories({ after, before, limit: 100, cursor }).then((result) => {
      setPage((current) => current.rangeKey === rangeKey ? { ...current, memories: [...current.memories, ...result.memories], nextCursor: result.nextCursor } : current);
    }).catch((loadError: unknown) => {
      setLoadMoreError(loadError instanceof Error ? loadError.message : 'Could not load more memories.');
    }).finally(() => setLoadingMore(false));
  }, [after, before, loadingMore, page.nextCursor, page.rangeKey, rangeKey]);

  return <ScreenFrame header={<ScreenHeader title="Monthly overview" onBack={goBack} />}>
    <FlatList
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ paddingHorizontal: layout.gutter, paddingBottom: spacing.xxl }}
      data={memories}
      keyExtractor={(memory) => memory.id}
      renderItem={({ item }) => <MemoryRow memory={item} onPress={() => void openMemory(item)} />}
      ListHeaderComponent={<MonthlyOverviewScreen monthDate={monthDate} memories={memories} totalCount={totalCount} nextCursor={loading ? null : page.nextCursor} loading={loading} error={error} onOpenMemory={(memory) => void openMemory(memory)} />}
      ListFooterComponent={<>{loadMoreError ? <Text style={styles.loadMoreError}>{loadMoreError}</Text> : null}{!error && page.nextCursor && <LoadMoreButton loading={loadingMore} label={`Load ${Math.max(0, (totalCount ?? memories.length) - memories.length)} more memories`} onPress={loadMore} />}</>}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor={colors.blueDeep} colors={[colors.blueDeep]} />}
    />
  </ScreenFrame>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({ loadMoreError: { marginTop: spacing.md, color: colors.danger, textAlign: 'center', ...text.caption } });
}
