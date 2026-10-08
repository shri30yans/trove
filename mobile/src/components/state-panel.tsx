import type { ComponentProps } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button } from './button';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { layout, radii, spacing, text, type Palette } from '../theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

/** The one loading / empty / error surface. `bare` drops the card chrome for use inside a panel. */
export function StatePanel({ body, title, icon, loading = false, action, onAction, bare = false }: {
  body: string;
  title?: string;
  icon?: IconName;
  loading?: boolean;
  action?: string;
  onAction?: () => void;
  bare?: boolean;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={[styles.panel, bare && styles.bare]}>
      {loading
        ? <ActivityIndicator color={colors.blueDeep} />
        : <View style={styles.mark}>{icon && <Ionicons name={icon} size={20} color={colors.foreground} />}</View>}
      {!!title && <Text style={styles.title}>{title}</Text>}
      <Text style={styles.body}>{body}</Text>
      {action && onAction && <Button label={action} variant="secondary" size="compact" onPress={onAction} />}
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    panel: { minHeight: 150, alignItems: 'center', justifyContent: 'center', gap: spacing.md, padding: spacing.xxxl, borderWidth: 1, borderColor: colors.border, borderRadius: radii.xl, backgroundColor: colors.surface },
    bare: { minHeight: 132, borderWidth: 0, backgroundColor: 'transparent', paddingHorizontal: layout.gutter },
    mark: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center', borderRadius: radii.pill, backgroundColor: colors.lavender },
    title: { maxWidth: 280, color: colors.foreground, ...text.section, textAlign: 'center' },
    body: { maxWidth: 270, color: colors.muted, ...text.body, textAlign: 'center' },
  });
}
