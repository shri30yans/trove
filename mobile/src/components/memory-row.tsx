import { MemoryImage } from './memory-image';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { kindColors, kindIcons, kindLabels, memoryDescription, memoryTitle, shortDate } from '../utils/memory-metadata';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { press, radii, spacing, text } from '../theme';
import type { Palette } from '../theme';
import type { Memory } from '../types';

const thumb = 44;
const thumbSmall = 34;

export function MemoryRow({ memory, onPress, compact = false }: { memory: Memory; onPress: () => void; compact?: boolean }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const preview = memory.previewUrl || (memory.localPending ? memory.localAssetUri : null);
  const label = memory.sourceDomain || memory.sourceApp || kindLabels[memory.kind];
  const size = compact ? thumbSmall : thumb;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${memoryTitle(memory)}, ${label}`}
      style={({ pressed }) => [styles.row, compact && styles.rowCompact, pressed && press.rowPressed]}
    >
      {preview && memory.kind === 'image'
        ? <MemoryImage uri={preview} style={[styles.thumb, { width: size, height: size }]} resizeMode="cover" />
        : <View style={[styles.mark, { width: size, height: size, backgroundColor: kindColors(colors)[memory.kind] }]}>
          <Ionicons name={kindIcons[memory.kind]} size={compact ? 15 : 18} color={colors.foreground} />
        </View>}
      <View style={styles.copy}>
        <Text numberOfLines={1} style={styles.title}>{memoryTitle(memory)}</Text>
        <Text numberOfLines={compact ? 1 : 2} style={styles.summary}>{memoryDescription(memory)}</Text>
      </View>
      <View style={styles.meta}>
        <Text numberOfLines={1} style={styles.date}>{memory.localPending ? memory.localSyncState === 'uploading' ? 'Syncing' : memory.localSyncState === 'blocked' ? 'Error' : 'On device' : shortDate(memory.capturedAt)}</Text>
        <Text numberOfLines={1} style={styles.source}>{label}</Text>
      </View>
    </Pressable>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    row: { minHeight: 76, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, paddingVertical: spacing.lg, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
    rowCompact: { minHeight: 56, gap: spacing.md, paddingVertical: spacing.sm },
    mark: { alignItems: 'center', justifyContent: 'center', borderRadius: radii.sm, borderWidth: 1, borderColor: colors.border },
    thumb: { borderRadius: radii.sm, borderWidth: 1, borderColor: colors.border },
    copy: { flex: 1, minWidth: 0 },
    title: { color: colors.foreground, ...text.itemTitle },
    summary: { marginTop: spacing.xxs, color: colors.muted, ...text.caption },
    meta: { minWidth: 48, maxWidth: 88, alignItems: 'flex-end', gap: spacing.xs },
    date: { color: colors.muted, ...text.meta },
    source: { maxWidth: 88, color: colors.muted, ...text.meta },
  });
}
