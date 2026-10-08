import type { ComponentProps } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button } from './button';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { radii, spacing, text, type Palette } from '../theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

/** Every inline status band: sync notices, pending saves, retryable errors, hints. */
export function Notice({ body, title, icon, tone = 'danger', action, onPress }: {
  body: string;
  title?: string;
  icon?: IconName;
  tone?: 'danger' | 'info' | 'neutral';
  action?: string;
  onPress?: () => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={[styles.notice, styles[tone]]}>
      {icon && <Ionicons name={icon} size={18} color={tone === 'danger' ? colors.danger : colors.foreground} />}
      <View style={styles.copy}>
        {!!title && <Text style={styles.title}>{title}</Text>}
        <Text style={[styles.body, tone === 'danger' && !title && styles.bodyDanger]}>{body}</Text>
      </View>
      {action && onPress && <Button label={action} variant="quiet" size="compact" onPress={onPress} />}
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    notice: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.lg, borderRadius: radii.md },
    danger: { backgroundColor: colors.dangerTint },
    info: { backgroundColor: colors.icyBlue },
    neutral: { backgroundColor: colors.thistle },
    copy: { flex: 1, minWidth: 0, gap: spacing.xxs },
    title: { color: colors.foreground, ...text.buttonSmall, fontWeight: '700' },
    body: { color: colors.muted, ...text.body },
    bodyDanger: { color: colors.danger, ...text.caption },
  });
}
