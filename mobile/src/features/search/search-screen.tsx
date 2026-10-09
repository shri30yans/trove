import { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSearchHistory } from './use-search-history';
import { Ionicons } from '@expo/vector-icons';
import { ActionSheet, Button, ErrorNotice, DateRangeCalendar, Eyebrow, IconButton, MemoryGrid, Pill, ScreenHeader, StatePanel, ScreenFrame, TextField, Notice, memoryTypePillItems } from '../../components';
import { calendarBounds, rangeLabel } from '../../components/calendar-range';
import type { CalendarRange } from '../../components';
import { useKeyboardOnScreenFocus } from '../../hooks/use-keyboard-on-screen-focus';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { iconSize, layout, press, spacing, text, type Palette } from '../../theme';
import type { Memory, Space } from '../../types';
import type { SearchMode, SearchRange } from './use-trove-search';

const dateRanges = [{ label: 'Any time', days: null }, { label: 'Past week', days: 7 }, { label: 'Past month', days: 30 }, { label: 'Past year', days: 365 }];

export function SearchScreen({ error, onRetry, query, tag, onTagChange, onQueryChange, queryKind, searchMode, onSearchModeChange, onKindChange, onRangeChange, results, loading, refreshing, spaces, spaceId, periodLabel, onSpaceChange, onRefresh, onOpenMemory, onBack }:
  { error: string | null; onRetry: () => void; query: string; tag: string | null; onTagChange: (tag: string | null) => void; queryKind: string; searchMode: SearchMode; onSearchModeChange: (mode: SearchMode) => void; onQueryChange: (query: string) => void; onKindChange: (kind: string) => void; onRangeChange: (range: SearchRange | null) => void; results: Memory[]; loading: boolean; refreshing: boolean; spaces: Space[]; spaceId: string | null; periodLabel?: string; onSpaceChange: (spaceId: string | null) => void; onRefresh: () => void; onOpenMemory: (memory: Memory) => void; onBack: () => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const selectedSpaceName = spaces.find((space) => space.id === spaceId)?.name;
  const hasContent = !!query.trim() || !!tag || !!periodLabel || !!spaceId || queryKind !== 'all';
  const { history, historyError, rememberQuery, clearHistory } = useSearchHistory();
  const [filterOpen, setFilterOpen] = useState(false);
  const [customRange, setCustomRange] = useState<CalendarRange | null>(null);
  const hasFilters = queryKind !== 'all' || !!periodLabel || !!tag || searchMode === 'raw';
  const searchInputRef = useKeyboardOnScreenFocus();
  const chooseRange = (days: number | null) => {
    setCustomRange(null);
    if (!days) { onRangeChange(null); return; }
    const before = new Date();
    const after = new Date(); after.setDate(after.getDate() - days);
    onRangeChange({ after: after.toISOString(), before: before.toISOString(), label: `Past ${days} days` });
  };
  const chooseExactRange = (range: CalendarRange) => {
    setCustomRange(range);
    onRangeChange({ ...calendarBounds(range), label: rangeLabel(range) });
  };

  const kindLabel = memoryTypePillItems.find((item) => item.kind === queryKind)?.label;
  const heading = tag ? `#${tag} memories` : query.trim() ? 'Matching memories' : periodLabel ? `${periodLabel} memories` : kindLabel ? `${kindLabel} memories` : `${selectedSpaceName} memories`;

  return <ScreenFrame header={<ScreenHeader title="Search" onBack={onBack} />} footer={<View testID="search-dock" style={styles.searchRow}>
        <TextField testID="search-editor" containerStyle={styles.searchField} inputRef={searchInputRef} value={query} onChangeText={onQueryChange} onSubmitEditing={() => rememberQuery(query)} placeholder="Search memories" icon="search-outline" size="large" returnKeyType="search" autoCorrect={false} accessibilityLabel="Search your memories" onClear={() => onQueryChange('')} />
        <IconButton accessibilityLabel="Filter search" icon={hasFilters ? 'options' : 'options-outline'} size="large" variant={hasFilters ? 'tinted' : 'outline'} selected={hasFilters} onPress={() => setFilterOpen(true)} />
      </View>}>
    <View style={styles.topContent}>
      {error && <View style={styles.errorHost}><ErrorNotice error={error} onRetry={onRetry} /></View>}
      {tag && <View style={styles.activeTag}><Pill label={`#${tag}`} selected onPress={() => onTagChange(null)} accessibilityLabel={`Remove tag filter ${tag}`} /><Button label="Clear" variant="quiet" size="compact" onPress={() => onTagChange(null)} /></View>}
      <Eyebrow label="Spaces" style={styles.railLabel} />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.spaceRail}>
        <Pill label="All spaces" maxWidth={180} selected={!spaceId} onPress={() => onSpaceChange(null)} accessibilityLabel="Search every space" />
        {spaces.map((space) => <Pill key={space.id} label={space.name} maxWidth={180} selected={space.id === spaceId} onPress={() => onSpaceChange(space.id)} accessibilityLabel={`Search ${space.name}`} />)}
      </ScrollView>
    </View>

    {hasContent ? <MemoryGrid
      style={styles.resultsViewport}
      memories={results}
      onOpenMemory={onOpenMemory}
      listHeader={<>{historyError && <Notice body={historyError} />}<Eyebrow label={heading} style={styles.resultHeading} />{loading && results.length > 0 && <Notice body="Updating results…" />}</>}
      listEmpty={loading ? <StatePanel bare loading body="Looking through your Trove…" /> : <StatePanel bare icon="search-outline" body="No memories found." />}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.blueDeep} colors={[colors.blueDeep]} />}
      contentContainerStyle={styles.resultsContent}
    /> : <ScrollView style={styles.resultsViewport} contentContainerStyle={styles.resultsContent} keyboardShouldPersistTaps="handled" refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.blueDeep} colors={[colors.blueDeep]} />}>
      {historyError && <Notice body={historyError} />}
      {history.length ? <>
        <View style={styles.historyHeader}>
          <Eyebrow label="Recent searches" />
          <Button label="Clear" variant="quiet" size="compact" onPress={clearHistory} />
        </View>
        {history.map((entry) => <Pressable key={entry} style={({ pressed }) => [styles.historyRow, pressed && press.rowPressed]} onPress={() => { onQueryChange(entry); }} accessibilityRole="button" accessibilityLabel={`Search again for ${entry}`}>
          <Ionicons name="time-outline" size={iconSize.md} color={colors.muted} />
          <Text numberOfLines={1} style={styles.historyText}>{entry}</Text>
          <Ionicons name="arrow-up-left-box" size={iconSize.sm} color={colors.muted} />
        </Pressable>)}
      </> : <StatePanel bare icon="time-outline" body="Your recent searches will appear here." />}
    </ScrollView>}

    {filterOpen && <ActionSheet title="Filter search" onClose={() => setFilterOpen(false)}>
        <Eyebrow label="Search method" style={styles.sheetLabel} />
        <View style={styles.optionGrid}>
          <Pill label="Smart + text" selected={searchMode === 'hybrid'} onPress={() => onSearchModeChange('hybrid')} accessibilityLabel="Search by meaning and text" />
          <Pill label="Raw text" selected={searchMode === 'raw'} onPress={() => onSearchModeChange('raw')} accessibilityLabel="Search text only without embeddings" />
        </View>
        <Text style={styles.modeHelp}>{searchMode === 'raw' ? 'Matches saved words and phrases. Does not use embeddings.' : 'Combines matching text with related meaning when available.'}</Text>
        <Eyebrow label="Memory type" style={styles.sheetLabel} />
        <View style={styles.optionGrid}>{memoryTypePillItems.map((item) => <Pill key={item.kind} label={item.label} icon={item.icon} selected={queryKind === item.kind} onPress={() => onKindChange(item.kind)} />)}</View>
        <Eyebrow label="Date saved" style={styles.sheetLabel} />
        <View style={styles.optionGrid}>{dateRanges.map((range) => <Pill key={range.label} label={range.label} selected={range.days === null ? !periodLabel : periodLabel === `Past ${range.days} days`} onPress={() => chooseRange(range.days)} />)}</View>
        <Eyebrow label="Or pick exact dates" style={styles.sheetLabel} />
        <View style={styles.calendarHost}><DateRangeCalendar value={customRange} onChange={chooseExactRange} /></View>
        <Button label="Show results" size="large" fills onPress={() => setFilterOpen(false)} />
    </ActionSheet>}
  </ScreenFrame>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    errorHost: { paddingHorizontal: layout.gutter, paddingBottom: spacing.lg },
    topContent: { flexShrink: 0 },
    activeTag: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: layout.gutter, paddingTop: spacing.md },
    railLabel: { paddingHorizontal: layout.gutter },
    spaceRail: { gap: layout.railGap, paddingHorizontal: layout.gutter, paddingTop: spacing.md, paddingBottom: spacing.xxl },
    resultsViewport: { flex: 1 },
    resultsContent: { flexGrow: 1, paddingHorizontal: layout.gutter, paddingBottom: spacing.xxl },
    resultHeading: { marginVertical: spacing.lg },
    historyHeader: { marginTop: spacing.xxxl, marginBottom: spacing.md, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    historyRow: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
    historyText: { flex: 1, minWidth: 0, color: colors.foreground, ...text.itemTitle },
    searchRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    searchField: { flex: 1, minWidth: 0 },
    sheetLabel: { marginBottom: spacing.md },
    calendarHost: { marginBottom: layout.sectionGap },
    optionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: layout.sectionGap },
    modeHelp: { marginTop: -spacing.md, marginBottom: layout.sectionGap, color: colors.muted, ...text.caption },
  });
}
