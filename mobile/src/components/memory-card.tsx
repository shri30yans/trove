import { MemoryImage } from './memory-image';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { kindIcons, kindLabels, memoryDescription, memoryTitle, shortDate } from '../utils/memory-metadata';
import { DecorativeOrb } from './decorative-orb';
import { Tag } from './tag';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { fonts, glass, layout, press, radii, spacing, text } from '../theme';
import type { Palette } from '../theme';
import type { Memory } from '../types';

export function MemoryCard({ memory, onPress }: { memory: Memory; onPress: () => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const preview = memory.previewUrl || (memory.localPending ? memory.localAssetUri : null);
  const tint = memory.kind === 'image' ? colors.petal : memory.kind === 'video' ? colors.lavender : memory.kind === 'link' ? colors.icyBlue : colors.thistle;
  const excerpt = memory.userNote || memory.description || memory.contentText || memory.pageText || memory.sourceDomain || kindLabels[memory.kind];

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && press.pressed]} accessibilityRole="button" accessibilityLabel={`${memoryTitle(memory)}, ${kindLabels[memory.kind]}, saved ${shortDate(memory.capturedAt)}`}>
      {preview
        ? <MemoryImage uri={preview} style={styles.artwork} resizeMode="cover" />
        : <View style={[styles.artwork, styles.artworkEmpty, { backgroundColor: tint }]}>
          <DecorativeOrb seed={`memory-${memory.id}`} size={120} color={glass.veil} />
          <Tag size="micro" label={kindLabels[memory.kind]} icon={kindIcons[memory.kind]} tone="glass" />
          <Text numberOfLines={3} style={styles.excerpt}>{excerpt}</Text>
        </View>}
      <View style={styles.copy}>
        <Text numberOfLines={1} style={styles.title}>{memoryTitle(memory)}</Text>
        <View style={styles.meta}>
          <Text numberOfLines={1} style={styles.description}>{memory.localPending ? 'Waiting to sync' : memoryDescription(memory)}</Text>
          <Text style={styles.date}>{shortDate(memory.capturedAt)}</Text>
        </View>
      </View>
    </Pressable>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    card: { width: 192, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, borderRadius: radii.lg, backgroundColor: colors.surface },
    artwork: { width: '100%', height: 132 },
    artworkEmpty: { position: 'relative', overflow: 'hidden', justifyContent: 'flex-start', alignItems: 'flex-start', gap: spacing.sm, paddingHorizontal: layout.pad, paddingTop: spacing.lg },
    excerpt: { maxWidth: '100%', color: colors.foreground, fontFamily: fonts.display, ...text.body },
    copy: { minHeight: 62, justifyContent: 'center', gap: spacing.xs, paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
    title: { color: colors.foreground, ...text.itemTitle },
    meta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
    description: { flex: 1, minWidth: 0, color: colors.muted, ...text.caption },
    date: { color: colors.muted, ...text.meta },
  });
}
