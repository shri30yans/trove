import type { ReactNode } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import { StyleSheet, Text, View } from 'react-native';
import { useThemedStyles } from '../providers/theme-provider';
import { Button } from './button';
import { spacing, text, type Palette } from '../theme';

/** Title line above any content section, with an optional hint and trailing action. */
export function SectionHeading({ title, hint, action, onAction, trailing, style }: {
  title: string;
  hint?: string;
  action?: string;
  onAction?: () => void;
  trailing?: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={[styles.heading, style]}>
      <View style={styles.copy}>
        <Text style={styles.title}>{title}</Text>
        {!!hint && <Text style={styles.hint}>{hint}</Text>}
      </View>
      {action && onAction ? <Button label={action} variant="quiet" size="compact" onPress={onAction} /> : trailing}
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    heading: { minHeight: 38, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
    copy: { flex: 1, minWidth: 0, gap: spacing.xxs },
    title: { color: colors.foreground, ...text.section },
    hint: { color: colors.muted, ...text.caption },
  });
}
