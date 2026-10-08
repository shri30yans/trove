import type { ComponentProps } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import { StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { iconBadge, iconSize, radii, type Palette } from '../theme';

type IconName = ComponentProps<typeof Ionicons>['name'];
type BadgeSize = 'row' | 'mark' | 'preview';

const glyphSize: Record<BadgeSize, number> = { row: iconSize.md, mark: iconSize.lg, preview: iconSize.xl };

/** The tinted well that opens a row, card, or empty state. It marks, so it never presses. */
export function IconBadge({ icon, size = 'row', tint, style }: {
  icon: IconName;
  size?: BadgeSize;
  tint?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={[styles.base, size === 'mark' && styles.mark, size === 'preview' && styles.preview, !!tint && { backgroundColor: tint }, style]}>
      <Ionicons name={icon} size={glyphSize[size]} color={colors.foreground} />
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    base: { width: iconBadge.row, height: iconBadge.row, alignItems: 'center', justifyContent: 'center', borderRadius: radii.sm, backgroundColor: colors.lavender },
    mark: { width: iconBadge.mark, height: iconBadge.mark },
    preview: { width: iconBadge.preview, height: iconBadge.preview, borderRadius: radii.md },
  });
}
