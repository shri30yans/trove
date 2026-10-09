import type { ComponentProps } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { control, iconSize, press, radii, spacing, type Palette } from '../theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

/**
 * The only icon-only control. `outline` sits in headers, `tinted` marks an in-content
 * affordance, `plain` is a bare glyph that still keeps the shared touch target.
 */
export function IconButton({ icon, onPress, accessibilityLabel, variant = 'outline', size = 'default', glyphSize, tint, selected = false, expanded, loading = false, disabled = false, style }: {
  icon: IconName;
  onPress: () => void;
  accessibilityLabel: string;
  variant?: 'outline' | 'tinted' | 'plain';
  size?: 'small' | 'default' | 'large';
  glyphSize?: 'compact' | 'small' | 'default' | 'large';
  tint?: string;
  selected?: boolean;
  expanded?: boolean;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const busy = disabled || loading;
  const selectedFill = selected && variant !== 'plain';
  return (
    <Pressable
      onPress={onPress}
      disabled={busy}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: busy, selected, expanded }}
      hitSlop={variant === 'plain' ? spacing.md : undefined}
      android_ripple={null} // kills the platform focus rim, which lingers after a tap; `press.pressed` is the feedback
      style={({ pressed }) => [
        styles.base,
        size === 'large' && styles.large,
        variant === 'outline' && styles.outline,
        variant === 'tinted' && [styles.tinted, { backgroundColor: tint ?? colors.skyBlue }],
        variant === 'plain' && styles.plain,
        selectedFill && styles.selected,
        pressed && press.pressed,
        busy && press.disabled,
        style,
      ]}
    >
      {loading
        ? <ActivityIndicator size="small" color={selected ? colors.surface : colors.foreground} />
        : <Ionicons name={icon} size={glyphSize === 'compact' ? iconSize.sm : glyphSize === 'small' ? iconSize.md : glyphSize === 'large' ? iconSize.xl : glyphSize === 'default' ? iconSize.lg : size === 'large' ? iconSize.xl : size === 'small' ? iconSize.sm : iconSize.md} color={selectedFill ? colors.surface : colors.foreground} />}
    </Pressable>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    base: { width: control.default, height: control.default, alignItems: 'center', justifyContent: 'center', borderRadius: radii.sm },
    large: { width: control.large, height: control.large, borderRadius: radii.pill },
    outline: { borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
    tinted: { backgroundColor: colors.skyBlue },
    plain: { backgroundColor: 'transparent' },
    selected: { backgroundColor: colors.deep },
  });
}
