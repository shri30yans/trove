import type { ComponentProps } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { control, iconSize, press, radii, spacing, text, type Palette } from '../theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

/**
 * The single selectable filter control: type rails, Space pickers, and filter-sheet
 * options all resolve to this. Selected always means a dark fill, never a tint.
 */
export function Pill({ label, selected, onPress, icon, accessibilityLabel, maxWidth = 200 }: {
  label: string;
  selected: boolean;
  onPress: () => void;
  icon?: IconName;
  accessibilityLabel?: string;
  maxWidth?: number;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={accessibilityLabel || label}
      style={({ pressed }) => [
        styles.pill,
        { maxWidth },
        selected && styles.selected,
        pressed && press.pressed,
      ]}
    >
      {icon && <Ionicons name={icon} size={iconSize.sm} color={selected ? colors.surface : colors.foreground} />}
      <Text numberOfLines={1} ellipsizeMode="tail" style={[styles.label, selected && styles.labelSelected]}>{label}</Text>
    </Pressable>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    pill: { minWidth: control.default, minHeight: control.default, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, paddingHorizontal: spacing.xl, borderWidth: 1, borderColor: colors.border, borderRadius: radii.pill, backgroundColor: colors.surface },
    selected: { borderColor: colors.deep, backgroundColor: colors.deep },
    label: { color: colors.foreground, ...text.buttonSmall },
    labelSelected: { color: colors.surface },
  });
}
