import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { MemoryCard, StatePanel } from '../../components';
import { DecorativeOrb } from '../../components/decorative-orb';
import { memoryCountLabel } from '../../utils/memory-metadata';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { fonts, radii, spacing, text } from '../../theme';
import type { Palette } from '../../theme';
import type { Memory } from '../../types';

export function MonthlyOverviewScreen({ monthDate, memories, totalCount, nextCursor, loading, error, onOpenMemory }:
  { monthDate: string; memories: Memory[]; totalCount?: number; nextCursor: string | null; loading: boolean; error: string | null; onOpenMemory: (memory: Memory) => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const month = new Date(monthDate);
  const monthName = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(month);
  const monthOnly = new Intl.DateTimeFormat(undefined, { month: 'long', timeZone: 'UTC' }).format(month);
  const monthShortName = new Intl.DateTimeFormat(undefined, { month: 'short', timeZone: 'UTC' }).format(month);
  const kindNames: Record<Memory['kind'], string> = { link: 'link', image: 'photo', text: 'note', audio: 'audio file', video: 'video', file: 'file' };
  const byKind = new Map<Memory['kind'], number>();
  memories.forEach((memory) => byKind.set(memory.kind, (byKind.get(memory.kind) || 0) + 1));
  const kindSummary = [...byKind.entries()].slice(0, 3).map(([kind, count]) => {
    const label = kindNames[kind];
    return `${count} ${label}${count === 1 ? '' : 's'}`;
  }).join(' · ');

  return <>
    <View style={styles.monthHero}>
      <View style={styles.monthHeroArtwork}><DecorativeOrb seed={`monthly-overview-${monthDate}`} size={82} color={colors.lavender} /><Text style={styles.monthHeroDay}>{monthShortName.toUpperCase()}</Text><Text style={styles.monthHeroNumber}>{month.getUTCFullYear()}</Text></View>
      <View style={styles.monthHeroCopy}><Text style={styles.monthTitle}>{monthName}</Text><Text style={styles.monthCount}>{loading ? 'Gathering your memories…' : error ? 'Could not load this month' : totalCount === undefined ? 'Memories from this month' : `${memoryCountLabel(totalCount)} saved`}</Text>{!loading && !error && !nextCursor && kindSummary ? <Text style={styles.kindSummary}>{kindSummary}</Text> : null}</View>
    </View>

    <View style={styles.sectionHeader}><View><Text style={styles.sectionTitle}>Moments from {monthOnly}</Text><Text style={styles.sectionHint}>{!loading && totalCount !== undefined && totalCount > memories.length ? `Swipe to browse · ${memories.length} of ${totalCount} loaded` : 'Swipe to browse this month'}</Text></View><View style={styles.countBadge}><Text style={styles.countBadgeText}>{totalCount ?? memories.length}</Text></View></View>
    {loading && memories.length === 0 ? <View style={styles.loadingPanel}><ActivityIndicator color={colors.blueDeep} /></View>
      : memories.length ? <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator={false} decelerationRate="fast" contentContainerStyle={styles.memoryRail}>
        {memories.slice(0, 12).map((memory) => <MemoryCard key={memory.id} memory={memory} onPress={() => onOpenMemory(memory)} />)}
      </ScrollView> : null}

    <View style={styles.timelineHeader}><View><Text style={styles.sectionTitle}>All memories</Text><Text style={styles.sectionHint}>Newest first</Text></View></View>
    {error ? <StatePanel title="Couldn’t load this month" body={error} icon="cloud-offline-outline" bare />
      : loading && memories.length === 0 ? <View style={styles.loadingPanel}><ActivityIndicator color={colors.blueDeep} /></View>
        : !memories.length ? <StatePanel title="Nothing saved this month yet" body="Your saved links, notes, photos, and files will collect here." icon="bookmark-outline" bare /> : null}
  </>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    monthHero: { minHeight: 148, flexDirection: 'row', alignItems: 'center', gap: spacing.xxl, marginBottom: spacing.xxxxl, padding: spacing.xxl, borderWidth: 1, borderColor: colors.thistle, borderRadius: radii.xl, backgroundColor: colors.surface },
    monthHeroArtwork: { width: 92, height: 116, overflow: 'hidden', alignItems: 'center', justifyContent: 'center', borderRadius: radii.md, backgroundColor: colors.lavender },
    monthHeroDay: { color: colors.foreground, fontFamily: fonts.mono, fontSize: 11, letterSpacing: 1.2 },
    monthHeroNumber: { marginTop: spacing.xs, color: colors.foreground, ...text.display },
    monthHeroCopy: { flex: 1, minWidth: 0 },
    monthTitle: { marginTop: spacing.sm, color: colors.foreground, ...text.display },
    monthCount: { marginTop: spacing.sm, color: colors.foreground, ...text.buttonSmall },
    kindSummary: { marginTop: spacing.xs, color: colors.muted, ...text.meta },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.lg, marginBottom: spacing.lg },
    sectionTitle: { color: colors.foreground, fontSize: 17, fontWeight: '600', letterSpacing: -0.2 },
    sectionHint: { marginTop: spacing.xs, color: colors.muted, ...text.caption },
    countBadge: { minWidth: 28, height: 28, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.sm, borderRadius: radii.md, backgroundColor: colors.lavender },
    countBadgeText: { color: colors.foreground, textAlign: 'center', ...text.buttonSmall },
    memoryRail: { gap: spacing.lg, paddingRight: spacing.xxxl },
    timelineHeader: { marginTop: spacing.xxxxl, marginBottom: spacing.md },
    loadingPanel: { minHeight: 110, alignItems: 'center', justifyContent: 'center' },
  });
}
