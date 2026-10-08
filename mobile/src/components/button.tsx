import type { ComponentProps } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { control, iconSize, press, radii, spacing, text, type Palette } from '../theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

/**
 * The only button in the app. `primary` commits, `secondary` offers an equal-weight
 * alternative, `quiet` is a bare text action. Size steps match `control`.
 */
export function Button({ label, onPress, variant = 'primary', size = 'default', icon, iconPosition = 'left', loading = false, disabled = false, fills = false, style }: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger';
  size?: 'compact' | 'default' | 'large';
  icon?: IconName;
  iconPosition?: 'left' | 'right';
  loading?: boolean;
  disabled?: boolean;
  fills?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const quiet = variant === 'quiet';
  const onDark = variant === 'primary' || variant === 'danger';
  const glyph = icon && !loading ? <Ionicons key="icon" name={icon} size={size === 'compact' ? iconSize.sm : iconSize.md} color={onDark ? colors.surface : colors.foreground} /> : null;
  const labelNode = (
    <Text
      key="label"
      numberOfLines={1}
      style={[
        styles.label,
        size === 'compact' && styles.labelCompact,
        size === 'large' && styles.labelLarge,
        !onDark && styles.labelOnLight,
      ]}
    >
      {label}
    </Text>
  );
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      hitSlop={quiet ? spacing.lg : undefined}
      style={({ pressed }) => [
        styles.base,
        quiet ? styles.quiet : variant === 'danger' ? styles.danger : onDark ? styles.primary : styles.secondary,
        size === 'compact' && styles.compact,
        size === 'large' && styles.large,
        fills && styles.fills,
        style,
        pressed && press.pressed,
        (disabled || loading) && press.disabled,
      ]}
    >
      {loading
        ? <ActivityIndicator key="spinner" size="small" color={onDark ? colors.surface : colors.foreground} />
        : iconPosition === 'right' ? [labelNode, glyph] : [glyph, labelNode]}
    </Pressable>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    base: { minWidth: control.default, minHeight: control.default, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.md, paddingHorizontal: spacing.xxl, borderRadius: radii.pill },
    danger: { backgroundColor: colors.danger },
    primary: { backgroundColor: colors.deep },
    secondary: { borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
    quiet: { paddingHorizontal: spacing.xs, backgroundColor: 'transparent' },
    compact: { paddingHorizontal: spacing.xl },
    large: { minHeight: control.large, paddingHorizontal: spacing.xxxl },
    fills: { alignSelf: 'stretch', paddingHorizontal: spacing.xxxl },
    label: { color: colors.surface, ...text.button },
    labelCompact: { ...text.buttonSmall },
    labelLarge: { ...text.buttonLarge },
    labelOnLight: { color: colors.foreground },
  });
}
