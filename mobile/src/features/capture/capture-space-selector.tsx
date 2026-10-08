import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { control, iconSize, press, radii, spacing, text, type Palette } from '../../theme';
import type { Space } from '../../types';

/** A capture destination stays a compact label; only its choices open a menu. */
export function CaptureSpaceSelector({ spaces, selectedId, expanded, disabled, onToggle, onSelect }: {
  spaces: Space[];
  selectedId: string | null;
  expanded: boolean;
  disabled: boolean;
  onToggle: () => void;
  onSelect: (id: string | null) => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const selected = spaces.find((space) => space.id === selectedId);
  return <View style={styles.anchor}>
    <Pressable disabled={disabled} onPress={onToggle} accessibilityRole="button" accessibilityLabel="Choose a Space for this memory" accessibilityState={{ expanded, disabled }} style={({ pressed }) => [styles.button, pressed && press.pressed]}>
      <Text numberOfLines={1} style={styles.label}>{selected?.name ?? 'All memories'}</Text>
      <Ionicons name="chevron-down" size={iconSize.sm} color={colors.muted} />
    </Pressable>
    {expanded && <ScrollView style={styles.menu} keyboardShouldPersistTaps="always">
      {[{ id: null, name: 'All memories' }, ...spaces].map((space) => <Pressable key={space.id ?? 'all'} disabled={disabled} accessibilityRole="button" accessibilityLabel={space.id ? `Save in ${space.name}` : 'Save without a Space'} accessibilityState={{ selected: selectedId === space.id, disabled }} onPress={() => onSelect(space.id)} style={({ pressed }) => [styles.option, pressed && press.pressed]}>
        <Text numberOfLines={1} style={styles.label}>{space.name}</Text>
        {selectedId === space.id && <Ionicons name="checkmark" size={iconSize.md} color={colors.foreground} />}
      </Pressable>)}
    </ScrollView>}
  </View>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    anchor: { flex: 1 },
    button: { minHeight: control.large, flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    label: { flexShrink: 1, color: colors.foreground, ...text.input },
    menu: { position: 'absolute', bottom: '100%', left: 0, marginBottom: spacing.md, width: '100%', maxHeight: control.large * 3, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, backgroundColor: colors.surface },
    option: { minHeight: control.large, paddingHorizontal: spacing.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  });
}
