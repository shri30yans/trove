import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useWorkspaceActions, useWorkspaceData } from '../../providers/workspace-provider';
import { useTrovePreferences } from '../../providers/preferences-provider';
import { useTroveToastContext } from '../../providers/toast-provider';
import { useMemoryDetailsActions } from '../../providers/memory-details-provider';
import { ActionSheet, Button, CreateFab, IconButton, LoadMoreButton, MemoryTypePillRail, ScreenFrame, ScreenHeader, StatePanel } from '../../components';
import type { MemoryTypeFilter } from '../../components';
import { MemoryGrid } from '../../components/memory-grid';
import { useMoveMemories } from '../../features/spaces/use-move-memories';
import { useGoBack } from '../../hooks/use-go-back';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { layout, radii, spacing, text } from '../../theme';
import type { Palette } from '../../theme';
import { useSpaceMemories } from '../../features/spaces/use-space-memories';

const filterLabels: Record<MemoryTypeFilter, string> = {
  all: 'All', text: 'Notes', link: 'Links', image: 'Photos', video: 'Videos', audio: 'Audio', file: 'Files',
};

export default function SpaceDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <SpaceDetailScreen key={id} id={id} />;
}

function SpaceDetailScreen({ id }: { id: string }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const router = useRouter();
  const goBack = useGoBack();
  const { spaces } = useWorkspaceData();
  const { loadWorkspace, upsertMemory } = useWorkspaceActions();
  const { exportMemories } = useTrovePreferences();
  const { showToast } = useTroveToastContext();
  const { openMemory } = useMemoryDetailsActions();
  const [filter, setFilter] = useState<MemoryTypeFilter>('all');
  const { memories, hideMoved, load, loadMore, hasMore, loading, refreshing, loadingMore, error, loadMoreError } = useSpaceMemories(id, filter === 'all' ? undefined : filter);
  const [moveMenuOpen, setMoveMenuOpen] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const onMoveConfirmed = useCallback((memory: Parameters<typeof upsertMemory>[0]) => {
    upsertMemory(memory);
    hideMoved(new Set([memory.id]));
  }, [hideMoved, upsertMemory]);
  const moveRequest = useMoveMemories(onMoveConfirmed);
  const moving = moveRequest.isPending;
  const { mutateAsync: moveBatch } = moveRequest;
  const space = spaces.find((item) => item.id === id);

  const toggleSelection = useCallback((memoryId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(memoryId)) next.delete(memoryId);
      else next.add(memoryId);
      return next;
    });
  }, []);

  const moveSelected = useCallback(async (targetSpaceId: string, targetSpaceName: string) => {
    const targets = memories.filter((memory) => selectedIds.has(memory.id));
    if (!targets.length || moving) return;
    const result = await moveBatch({ memoryIds: targets.map((memory) => memory.id), fromSpaceId: id, toSpaceId: targetSpaceId });
    const movedIds = new Set(result.confirmedIds);
    setSelectedIds(new Set(targets.filter((memory) => !movedIds.has(memory.id)).map((memory) => memory.id)));
    if (movedIds.size === targets.length) setSelectionMode(false);
    setMoveMenuOpen(false);
    if (movedIds.size) showToast(`${movedIds.size} ${movedIds.size === 1 ? 'memory' : 'memories'} moved to ${targetSpaceName}`);
    if (movedIds.size < targets.length) showToast(`${targets.length - movedIds.size} ${targets.length - movedIds.size === 1 ? 'memory' : 'memories'} could not be moved.`);
    if (result.refreshRequired) showToast('Memories moved. Refresh your library to update the display.');
    void loadWorkspace(true).catch(() => showToast('Memories moved. Refresh your library to update its counts.'));
  }, [id, loadWorkspace, memories, selectedIds, showToast, moveBatch, moving]);

  const title = space?.name || 'Space';
  const memoryCount = space?.memoryCount ?? memories.length;
  const moveTargets = spaces.filter((item) => item.id !== id);

  return <ScreenFrame header={<ScreenHeader
        title={title}
        subtitle={`${memoryCount} ${memoryCount === 1 ? 'memory' : 'memories'} · Newest first`}
        onBack={goBack}
        actions={<>
          <IconButton icon={selectionMode ? 'checkbox' : 'checkbox-outline'} onPress={() => { setSelectionMode((current) => !current); setSelectedIds(new Set()); }} accessibilityLabel={selectionMode ? 'Exit selection' : 'Select memories'} />
          <IconButton icon="share-outline" onPress={() => void exportMemories(id)} accessibilityLabel="Share this Space" />
        </>}
      />} footer={selectionMode ? <View style={styles.moveBar}>
      <Text style={styles.moveBarCount}>{selectedIds.size} selected</Text>
      <Button variant="quiet" size="compact" label="Cancel" onPress={() => setSelectionMode(false)} />
      <Button size="compact" label="Move to Space" icon="arrow-forward-circle-outline" loading={moving} disabled={!selectedIds.size} onPress={() => setMoveMenuOpen(true)} />
    </View> : !selectionMode ? <View style={styles.fabHost}><CreateFab onPress={() => router.push({ pathname: '/capture', params: { spaceId: id } })} accessibilityLabel={`Create a memory in ${title}`} /></View> : undefined}>
    <MemoryTypePillRail selectedKind={filter} onSelect={(kind) => { setFilter(kind); setSelectedIds(new Set()); }} horizontalInset={layout.gutter} />
    {memories.length ? <MemoryGrid
      style={styles.scroll}
      contentContainerStyle={styles.content}
      memories={memories}
      onOpenMemory={(memory) => void openMemory(memory)}
      selectionMode={selectionMode}
      selectedIds={selectedIds}
      onToggleSelect={toggleSelection}
      listHeader={space?.description ? <Text style={styles.description}>{space.description}</Text> : null}
      listFooter={<>{hasMore && <LoadMoreButton loading={loadingMore} onPress={() => void loadMore()} />}{loadMoreError && <Text style={styles.loadMoreError}>{loadMoreError}</Text>}</>}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load()} tintColor={colors.blueDeep} />}
    /> : <ScrollView style={styles.scroll} contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load()} tintColor={colors.blueDeep} />}>
      {space?.description ? <Text style={styles.description}>{space.description}</Text> : null}
      {loading ? <StatePanel body="Gathering memories…" loading bare />
        : error ? <StatePanel body={error} icon="cloud-offline-outline" action="Try again" onAction={() => void load()} bare />
          : <><StatePanel title={filter === 'all' ? 'Nothing in this Space yet' : `No ${filterLabels[filter].toLowerCase()} yet`} body={hasMore ? 'More memories may match this filter.' : 'Add a memory here or move one in from its details.'} icon="albums-outline" bare />{hasMore && <LoadMoreButton loading={loadingMore} onPress={() => void loadMore()} />}{loadMoreError && <Text style={styles.loadMoreError}>{loadMoreError}</Text>}</>}
    </ScrollView>}
    {moveMenuOpen && <ActionSheet title="Move to Space" busy={moving} onClose={() => setMoveMenuOpen(false)}>
      {moveTargets.map((target) => <Button key={target.id} variant="quiet" label={target.name} disabled={moving} onPress={() => void moveSelected(target.id, target.name)} />)}
      {!moveTargets.length && <StatePanel bare body="Create another Space to move these memories into." action="Create Space" onAction={() => { setMoveMenuOpen(false); router.push('/space/new'); }} />}
    </ActionSheet>}
  </ScreenFrame>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    description: { color: colors.muted, ...text.subtitle, marginBottom: spacing.xl },
    fabHost: { alignItems: 'flex-end' },
    scroll: { flex: 1 },
    content: { paddingHorizontal: layout.gutter, paddingBottom: spacing.xxl },
    moveBar: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg, padding: spacing.xl, borderWidth: 1, borderColor: colors.border, borderRadius: radii.lg, backgroundColor: colors.surface },
    moveBarCount: { flex: 1, color: colors.foreground, ...text.buttonSmall },
    loadMoreError: { marginTop: spacing.md, color: colors.danger, textAlign: 'center', ...text.subtitle },
  });
}
