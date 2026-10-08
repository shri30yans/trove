import type { StyleProp, TextStyle } from 'react-native';
import { StyleSheet, Text } from 'react-native';
import { useThemedStyles } from '../providers/theme-provider';
import { text, type Palette } from '../theme';

/** The small tracked label that opens every section, group, or field. */
export function Eyebrow({ label, style }: { label: string; style?: StyleProp<TextStyle> }) {
  const styles = useThemedStyles(makeStyles);
  return <Text numberOfLines={1} style={[styles.eyebrow, style]}>{label}</Text>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    eyebrow: { color: colors.muted, ...text.eyebrow, textTransform: 'uppercase' },
  });
}
