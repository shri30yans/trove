import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useThemedStyles } from '../providers/theme-provider';
import { IconButton } from './icon-button';
import { control, layout, spacing, text, type Palette } from '../theme';

/** Title chrome for every screen: plain back glyph inline with the display title, optional trailing actions. */
export function ScreenHeader({ title, subtitle, onBack, actions }: {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  actions?: ReactNode;
}) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.header}>
      <View style={styles.titleRow}>
        {onBack && <IconButton icon="arrow-back" variant="plain" onPress={onBack} accessibilityLabel="Back" />}
        <Text numberOfLines={1} style={styles.title}>{title}</Text>
        <View style={styles.spacer} />
        {actions}
      </View>
      {!!subtitle && <Text style={[styles.subtitle, !!onBack && styles.subtitleIndented]}>{subtitle}</Text>}
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    header: { paddingBottom: layout.headerGap },
    titleRow: { minHeight: control.default, flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
    title: { flexShrink: 1, color: colors.foreground, ...text.page },
    spacer: { flex: 1, marginLeft: spacing.md },
    subtitle: { marginTop: spacing.sm, color: colors.muted, ...text.subtitle },
    subtitleIndented: { marginLeft: control.default + spacing.xs },
  });
}
