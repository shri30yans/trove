import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Notice } from '../../components';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { radii, spacing, text, type Palette } from '../../theme';
import type { StoragePlan } from '../../types';

export function PlanStorageCard({ plan, loading, error }: { plan: StoragePlan | null; loading: boolean; error: string | null }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  if (loading && !plan) return <View style={styles.loading}><ActivityIndicator color={colors.blueDeep} /><Text style={styles.secondary}>Loading plan and storage…</Text></View>;
  if (error && !plan) return <Notice title="Storage details unavailable" body={error} tone="danger" icon="alert-circle-outline" />;
  if (!plan) return null;

  const percentUsed = Math.min(100, Math.round((plan.storageUsedBytes / plan.storageLimitBytes) * 100));
  const full = plan.storageUsedBytes >= plan.storageLimitBytes;
  return <View style={styles.card}>
    <View style={styles.header}>
      <View style={styles.planIcon}><Ionicons name="cloud-outline" size={20} color={colors.blueDeep} /></View>
      <View style={styles.copy}>
        <Text style={styles.planName}>{plan.name} plan</Text>
        <Text style={styles.secondary}>{formatStorage(plan.storageLimitBytes)} storage</Text>
      </View>
      <Text style={styles.badge}>{plan.id === 'paid' ? 'PAID' : 'FREE'}</Text>
    </View>
    <View accessibilityRole="progressbar" accessibilityLabel="Storage used" accessibilityValue={{ min: 0, max: 100, now: percentUsed }} style={styles.track}>
      <View style={[styles.fill, full && styles.full, { width: `${percentUsed}%` }]} />
    </View>
    <View style={styles.usageRow}>
      <Text style={styles.usage}>{formatStorage(plan.storageUsedBytes)} used or reserved</Text>
      <Text style={styles.secondary}>{percentUsed}%</Text>
    </View>
        <Text style={styles.footnote}>{full ? 'Storage is full. New file uploads will stay on this device until your plan changes.' : `${formatStorage(plan.storageRemainingBytes)} available`}</Text>
    {error && <Text style={styles.error}>{error}</Text>}
  </View>;
}

function formatStorage(bytes: number) {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(bytes % 1_000_000_000 === 0 ? 0 : 1)} GB`;
  if (bytes >= 10_000_000) return `${Math.round(bytes / 1_000_000)} MB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes <= 0) return '0 MB';
  return `${Math.ceil(bytes / 1_000)} KB`;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    card: { padding: spacing.xl, borderWidth: 1, borderColor: colors.borderSoft, borderRadius: radii.xl, backgroundColor: colors.surface },
    header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    planIcon: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center', borderRadius: radii.pill, backgroundColor: colors.icyBlue },
    copy: { flex: 1, gap: spacing.xxs },
    planName: { color: colors.foreground, ...text.button },
    secondary: { color: colors.muted, ...text.caption },
    badge: { color: colors.blueDeep, ...text.meta, fontWeight: '700' },
    track: { height: 8, overflow: 'hidden', marginTop: spacing.xl, borderRadius: radii.pill, backgroundColor: colors.border },
    fill: { height: '100%', borderRadius: radii.pill, backgroundColor: colors.blueDeep },
    full: { backgroundColor: colors.danger },
    usageRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.md, marginTop: spacing.md },
    usage: { color: colors.foreground, ...text.caption, fontWeight: '600' },
    footnote: { marginTop: spacing.sm, color: colors.muted, ...text.caption },
    error: { marginTop: spacing.sm, color: colors.danger, ...text.caption },
    loading: { minHeight: 86, flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.xl, borderWidth: 1, borderColor: colors.borderSoft, borderRadius: radii.xl, backgroundColor: colors.surface },
  });
}
