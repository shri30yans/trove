import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button, Eyebrow, IconBadge, Notice } from '../../components';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { iconSize, radii, spacing, switchControl, text, themeOrder, themes, type Palette, type ThemeId } from '../../theme';
import type { SyncStatus } from '../sync/sync-status';
import type { StoragePlan } from '../../types';
import { PlanStorageCard } from './plan-storage-card';
import { formatLastSynced } from '../../utils/format-last-synced';

export function ProfileScreen({ backgroundSync, localSettingsLoaded, theme, themeLoaded, syncStatus, pendingCount, syncing, lastSyncedAt, loading, plan, planLoading, planError, onToggleSync, onChangeTheme, onSyncNow, onOpenCloud, onExport, onOpenAccount }:
  { localSettingsLoaded: boolean; backgroundSync: boolean; theme: ThemeId; themeLoaded: boolean; syncStatus: SyncStatus; pendingCount: number; syncing: boolean; lastSyncedAt: string | null; loading: boolean; plan: StoragePlan | null; planLoading: boolean; planError: string | null; onToggleSync: (value: boolean) => void; onChangeTheme: (id: ThemeId) => void; onSyncNow: () => void; onOpenCloud: () => void; onExport: () => void; onOpenAccount: () => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const [themeRail, setThemeRail] = useState({ width: 0, contentWidth: 0, offset: 0 });
  const railWidth = Math.min(themeRail.width, 104);
  const thumbWidth = themeRail.contentWidth > 0 ? Math.max(24, railWidth * Math.min(1, themeRail.width / themeRail.contentWidth)) : railWidth;
  const scrollRange = Math.max(0, themeRail.contentWidth - themeRail.width);
  const thumbOffset = scrollRange > 0 ? Math.max(0, Math.min(1, themeRail.offset / scrollRange)) * (railWidth - thumbWidth) : 0;
  const syncLabel = syncStatus.state === 'loading' ? 'Checking sync…'
    : syncStatus.state === 'blocked' && !pendingCount ? 'Sync unavailable'
      : syncStatus.state === 'uploading' || syncing ? `Syncing · ${pendingCount}`
        : pendingCount ? `Not uploaded · ${pendingCount}` : 'Up to date';
  const syncDetail = syncStatus.state === 'blocked'
    ? null
    : syncStatus.state === 'offline' ? 'Waiting for a connection.'
      : syncStatus.state === 'retrying' ? 'Waiting to sync.'
        : null;
  const blockedReason = syncStatus.state === 'blocked' ? syncStatus.detail ?? syncStatus.message : null;
  return <>
    <Eyebrow label="Plan & storage" style={styles.sectionLabel} />
    <PlanStorageCard plan={plan} loading={planLoading} error={planError} />
    <Eyebrow label="Sync" style={[styles.groupGap, styles.sectionLabel]} />
    <View style={styles.settingsCard}>
      <Pressable onPress={onOpenCloud} accessibilityRole="button" accessibilityLabel="Open cloud sync and processing details" style={({ pressed }) => [styles.syncSummary, pressed && styles.pressed]}>
        <View style={[styles.syncMark, { backgroundColor: syncStatus.state === 'blocked' ? colors.dangerTint : colors.icyBlue }]}>
          <Ionicons name={syncStatus.state === 'complete' ? 'cloud-done-outline' : syncStatus.state === 'blocked' ? 'alert-circle-outline' : syncStatus.state === 'offline' ? 'cloud-offline-outline' : syncStatus.state === 'paused' ? 'pause-circle-outline' : 'cloud-upload-outline'} size={19} color={syncStatus.state === 'blocked' ? colors.danger : colors.blueDeep} />
        </View>
        <View style={styles.syncCopy}>
          <Text style={styles.syncSummaryText}>{syncLabel}</Text>
          {syncDetail && <Text style={styles.settingDescription}>{syncDetail}</Text>}
          <Text style={styles.syncLast}>{formatLastSynced(lastSyncedAt)}</Text>
        </View>
        {pendingCount > 0 && <Button variant="secondary" size="compact" label={syncing ? 'Syncing…' : syncStatus.state === 'blocked' ? 'Retry' : 'Sync now'} loading={syncing} disabled={syncStatus.state === 'offline'} onPress={onSyncNow} />}
        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
      </Pressable>
      {blockedReason && <View style={styles.syncNotice}><Notice body={blockedReason} tone="danger" /></View>}
      <SettingRow icon={backgroundSync ? 'cloud-upload-outline' : 'cloud-outline'} title="Automatic sync" description={backgroundSync ? 'On · Sync while Trove is open' : 'Off · Sync manually'} value={backgroundSync} onChange={onToggleSync} disabled={!localSettingsLoaded} />
    </View>
    <Eyebrow label="Your data" style={[styles.groupGap, styles.sectionLabel]} />
    <View style={styles.settingsCard}>
      <View style={styles.dataRow}><IconBadge icon="download-outline" /><View style={styles.settingCopy}><Text style={styles.settingTitle}>Export your data</Text><Text style={styles.finePrint}>Download ZIP</Text></View><Button variant="primary" size="default" label="Export" onPress={onExport} /></View>
    </View>
    <Eyebrow label="Appearance" style={[styles.groupGap, styles.sectionLabel]} />
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.themeRail}
      onLayout={(event) => { const width = event.nativeEvent.layout.width; setThemeRail((current) => ({ ...current, width })); }}
      onContentSizeChange={(contentWidth) => setThemeRail((current) => ({ ...current, contentWidth }))}
      onScroll={(event) => { const offset = event.nativeEvent.contentOffset.x; setThemeRail((current) => ({ ...current, offset })); }} scrollEventThrottle={16}>
      {themeOrder.map((id) => <Pressable key={id} onPress={() => onChangeTheme(id)} disabled={!themeLoaded} accessibilityRole="button" accessibilityLabel={`${themes[id].label} theme`} accessibilityState={{ selected: theme === id, disabled: !themeLoaded }} style={({ pressed }) => [styles.themeChip, theme === id && styles.themeChipSelected, pressed && styles.pressed]}>
        <View style={[styles.themeSwatch, { backgroundColor: themes[id].colors.background }]}>
          <View style={[styles.themeSwatchDeep, { backgroundColor: themes[id].colors.deep }]} />
          <View style={[styles.themeSwatchTint, { backgroundColor: themes[id].colors.lavender }]} />
        </View>
        <Text style={[styles.themeLabel, theme === id ? styles.themeLabelSelected : styles.themeLabelMuted]}>{themes[id].label}</Text>
      </Pressable>)}
    </ScrollView>
    <View accessible={false} style={[styles.themeScrollTrack, { width: railWidth }]}><View style={[styles.themeScrollThumb, { width: thumbWidth, transform: [{ translateX: thumbOffset }] }]} /></View>
    <>
      <Eyebrow label="Account" style={[styles.groupGap, styles.sectionLabel]} />
      <View style={styles.settingsCard}>
        <Pressable onPress={onOpenAccount} accessibilityRole="button" accessibilityLabel="Open account settings" style={({ pressed }) => [styles.accountRow, pressed && styles.pressed]}>
          <IconBadge icon="person-circle-outline" />
          <View style={styles.settingCopy}><Text style={styles.settingTitle}>Account settings</Text><Text style={styles.settingDescription}>Sign out or manage account deletion</Text></View>
          <Ionicons name="chevron-forward" size={16} color={colors.muted} />
        </Pressable>
      </View>
    </>
    {loading && <View style={styles.profileLoading}><ActivityIndicator color={colors.blueDeep} /></View>}
  </>;
}

function SettingRow({ icon, title, description, value, onChange, disabled = false }: { icon: keyof typeof Ionicons.glyphMap; title: string; description: string; value: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return <View style={styles.settingRow}>
    <IconBadge icon={icon} />
    <View style={styles.settingCopy}><Text style={styles.settingTitle}>{title}</Text><Text style={styles.settingDescription}>{description}</Text></View>
    <Pressable onPress={() => onChange(!value)} disabled={disabled} accessibilityRole="switch" accessibilityLabel={title} accessibilityState={{ checked: value, disabled }} style={[styles.switchControl, disabled && styles.switchDisabled]}>
      <View style={[styles.switchTrack, value ? styles.switchOn : styles.switchOff]}>
        <View style={[styles.switchThumb, !value && styles.switchThumbOff]}><Ionicons name={value ? 'checkmark' : 'remove'} size={iconSize.sm} color={value ? colors.deep : colors.surface} /></View>
      </View>
    </Pressable>
  </View>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    sectionLabel: { marginBottom: spacing.lg },
    pressed: { opacity: 0.8 },
    syncSummary: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingHorizontal: spacing.xl, minHeight: 68, paddingVertical: spacing.lg },
    syncMark: { width: 38, height: 38, borderRadius: radii.pill, alignItems: 'center', justifyContent: 'center' },
    syncCopy: { flex: 1, minWidth: 0, gap: spacing.xxs },
    syncSummaryText: { color: colors.foreground, ...text.button },
    syncLast: { color: colors.muted, ...text.meta },
    syncNotice: { paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
    themeRail: { gap: spacing.md, paddingBottom: spacing.md },
    themeScrollTrack: { height: spacing.xs, marginTop: spacing.sm, alignSelf: 'center', borderRadius: radii.pill, backgroundColor: colors.border },
    themeScrollThumb: { height: spacing.xs, borderRadius: radii.pill, backgroundColor: colors.muted },
    themeChip: { width: 104, alignItems: 'center', gap: spacing.sm, padding: spacing.md, borderWidth: 1, borderColor: colors.borderSoft, borderRadius: radii.lg, backgroundColor: colors.surface },
    themeChipSelected: { borderColor: colors.blueDeep, backgroundColor: colors.thistle },
    themeSwatch: { width: '100%', height: 44, alignItems: 'center', justifyContent: 'center', gap: spacing.xs, borderRadius: radii.sm, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' },
    themeSwatchDeep: { width: '60%', height: 14, borderRadius: radii.pill },
    themeSwatchTint: { width: '38%', height: 8, borderRadius: radii.pill },
    themeLabel: { ...text.caption, fontWeight: '600' },
    themeLabelSelected: { color: colors.foreground },
    themeLabelMuted: { color: colors.muted },
    groupGap: { marginTop: spacing.xxxxl },
    settingsCard: { overflow: 'hidden', borderWidth: 1, borderColor: colors.borderSoft, borderRadius: radii.xl, backgroundColor: colors.surface },
    settingRow: { minHeight: 78, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, paddingHorizontal: spacing.xl, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
    switchControl: { width: switchControl.width, height: switchControl.height, alignItems: 'center', justifyContent: 'center' },
    switchTrack: { width: switchControl.trackWidth, height: switchControl.trackHeight, padding: spacing.xs, borderRadius: radii.pill, justifyContent: 'center' },
    switchOn: { backgroundColor: colors.deep, alignItems: 'flex-end' },
    switchOff: { backgroundColor: colors.border, alignItems: 'flex-start' },
    switchThumb: { width: switchControl.thumbSize, height: switchControl.thumbSize, borderRadius: radii.pill, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
    switchThumbOff: { backgroundColor: colors.muted },
    switchDisabled: { opacity: 0.5 },
    settingCopy: { flex: 1 },
    settingTitle: { color: colors.foreground, ...text.button },
    settingDescription: { marginTop: spacing.xs, color: colors.muted, ...text.caption },
    finePrint: { marginTop: spacing.xs, color: colors.muted, ...text.caption },
    dataRow: { minHeight: 82, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, paddingHorizontal: spacing.xl },
    profileLoading: { padding: spacing.xl },
    accountRow: { minHeight: 76, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, paddingHorizontal: spacing.xl },
  });
}
