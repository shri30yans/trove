import { ScrollView, StyleSheet } from 'react-native';
import type { ComponentProps } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Pill } from './pill';
import { control, layout, spacing } from '../theme';

export type MemoryTypeFilter = 'text' | 'link' | 'image' | 'video' | 'audio' | 'file' | 'all';

type IconName = ComponentProps<typeof Ionicons>['name'];

export const memoryTypePillItems: { kind: MemoryTypeFilter; label: string; icon: IconName }[] = [
  { kind: 'text', label: 'Notes', icon: 'document-text-outline' },
  { kind: 'link', label: 'Links', icon: 'link-outline' },
  { kind: 'image', label: 'Photos', icon: 'images-outline' },
  { kind: 'video', label: 'Videos', icon: 'videocam-outline' },
  { kind: 'file', label: 'Files', icon: 'document-attach-outline' },
  { kind: 'all', label: 'All', icon: 'grid-outline' },
];

export function MemoryTypePillRail({ onSelect, selectedKind, horizontalInset = 0 }: {
  onSelect: (kind: MemoryTypeFilter) => void;
  selectedKind?: MemoryTypeFilter;
  horizontalInset?: number;
}) {
  return (
    <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator={false} style={styles.viewport} contentContainerStyle={[styles.rail, { paddingHorizontal: horizontalInset }]}>
      {memoryTypePillItems.map((item) => (
        <Pill
          key={item.kind}
          label={item.label}
          icon={item.icon}
          maxWidth={130}
          selected={selectedKind === item.kind}
          onPress={() => onSelect(item.kind)}
          accessibilityLabel={`Browse ${item.label.toLowerCase()}`}
        />
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  viewport: { flexGrow: 0, flexShrink: 0, minHeight: control.default + spacing.xs * 2 },
  rail: { alignItems: 'center', gap: layout.railGap, paddingVertical: spacing.xs },
});
