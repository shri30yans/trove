import type { ComponentProps } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { Palette, fonts, glass, radii, spacing, text } from '../theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

/** A read-only marker on content: memory type, count, quick-save stamp. Never tappable. */
export function Tag({ label, icon, tone = 'tint', size = 'default' }: {
  label: string;
  icon?: IconName;
  tone?: 'tint' | 'lavender' | 'glass' | 'surface';
  size?: 'micro' | 'default';
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const micro = size === 'micro';
  return (
    <View style={[styles.base, micro && styles.micro, styles[tone]]}>
      {icon && <Ionicons name={icon} size={micro ? 9 : 12} color={colors.foreground} />}
      <Text numberOfLines={1} style={[styles.label, micro && styles.labelMicro]}>{label}</Text>
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    base: { minHeight: 24, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, paddingHorizontal: spacing.md, borderRadius: radii.pill },
    micro: { minHeight: 18, paddingHorizontal: spacing.sm, borderRadius: radii.xs, gap: spacing.xs },
    tint: { backgroundColor: colors.icyBlue },
    lavender: { backgroundColor: colors.lavender },
    glass: { backgroundColor: glass.strong },
    surface: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
    label: { color: colors.foreground, ...text.buttonSmall },
    labelMicro: { color: colors.foreground, fontFamily: fonts.mono, fontSize: 8, lineHeight: 11, letterSpacing: 0.4 },
  });
}
