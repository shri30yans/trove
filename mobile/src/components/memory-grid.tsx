import { MemoryImage } from './memory-image';
import { FlatList, Pressable, StyleSheet, Text, View, type ListRenderItemInfo, type RefreshControlProps, type StyleProp, type ViewStyle } from 'react-native';
import type { ReactElement } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { kindColors, kindIcons, memoryTitle, shortDate } from '../utils/memory-metadata';
import { Tag } from './tag';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { layout, press, radii, spacing, text } from '../theme';
import type { Palette } from '../theme';
import type { Memory } from '../types';

type TileLabel = (memory: Memory) => string;

const tileLabel: TileLabel = (memory) => memory.sourceDomain || memory.sourceApp || memory.kind;

export function MemoryGrid({ memories, onOpenMemory, selectionMode = false, selectedIds, onToggleSelect, listHeader, listFooter, listEmpty, refreshControl, contentContainerStyle, style }: {
  memories: Memory[];
  onOpenMemory: (memory: Memory) => void;
  selectionMode?: boolean;
  selectedIds?: Set<string>;
  onToggleSelect?: (memoryId: string) => void;
  listHeader?: ReactElement | null;
  listFooter?: ReactElement | null;
  listEmpty?: ReactElement | null;
  refreshControl?: ReactElement<RefreshControlProps>;
  contentContainerStyle?: StyleProp<ViewStyle>;
  style?: StyleProp<ViewStyle>;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const memoryColors = kindColors(colors);
  const renderItem = ({ item: memory }: ListRenderItemInfo<Memory>) => {
    const preview = memory.previewUrl || (memory.localPending ? memory.localAssetUri : null);
    const image = preview && (memory.kind === 'image' || memory.kind === 'video');
    const detail = memory.userNote || memory.description || memory.contentText || memory.pageText || memory.sourceDomain || memoryTitle(memory);
    const selected = !!selectedIds?.has(memory.id);
    return <Pressable
      onPress={() => selectionMode ? onToggleSelect?.(memory.id) : onOpenMemory(memory)}
      accessibilityRole="button"
      accessibilityLabel={selectionMode ? `${memoryTitle(memory)}, ${selected ? 'selected' : 'not selected'}` : `${memoryTitle(memory)}, ${tileLabel(memory)}, saved ${shortDate(memory.capturedAt)}`}
      style={({ pressed }) => [styles.tile, { backgroundColor: memoryColors[memory.kind] }, selected && styles.tileSelected, pressed && press.pressed]}
    >
      {image && <MemoryImage uri={preview} style={styles.preview} resizeMode="cover" />}
      {selectionMode && <View style={[styles.selectBadge, selected && styles.selectBadgeOn]}>
        <Ionicons name="checkmark" size={14} color={selected ? colors.surface : 'transparent'} />
      </View>}
      <View style={styles.tileContent}>
        <Tag label={tileLabel(memory)} icon={kindIcons[memory.kind]} tone="glass" />
        <View style={styles.tileCopy}>
          <Text numberOfLines={2} style={styles.title}>{memoryTitle(memory)}</Text>
          <Text numberOfLines={2} style={styles.description}>{detail}</Text>
          <Text style={styles.date}>{shortDate(memory.capturedAt)}</Text>
        </View>
      </View>
    </Pressable>;
  };
  return <FlatList
    style={style}
    data={memories}
    renderItem={renderItem}
    keyExtractor={(memory) => memory.id}
    numColumns={2}
    columnWrapperStyle={styles.row}
    contentContainerStyle={[styles.grid, contentContainerStyle]}
    extraData={selectedIds}
    ListHeaderComponent={listHeader}
    ListFooterComponent={listFooter}
    ListEmptyComponent={listEmpty}
    refreshControl={refreshControl}
  />;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    grid: { rowGap: spacing.lg },
    row: { columnGap: spacing.lg },
    tile: { flex: 1, minHeight: 174, overflow: 'hidden', borderRadius: radii.lg },
    tileSelected: { borderWidth: 2, borderColor: colors.deep },
    selectBadge: { position: 'absolute', top: spacing.md, right: spacing.md, zIndex: 2, width: 24, height: 24, alignItems: 'center', justifyContent: 'center', borderRadius: radii.pill, borderWidth: 1.5, borderColor: colors.deep, backgroundColor: 'rgba(255,255,255,0.9)' },
    selectBadgeOn: { backgroundColor: colors.deep },
    preview: { width: '100%', height: 84 },
    tileContent: { flex: 1, justifyContent: 'space-between', padding: spacing.lg },
    tileCopy: { gap: spacing.xs, paddingTop: layout.pad },
    title: { color: colors.foreground, ...text.itemTitle },
    description: { color: colors.secondary, ...text.caption },
    date: { marginTop: spacing.xs, color: colors.secondary, ...text.meta },
  });
}
