import { MemoryImage } from '../../components/memory-image';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { IconBadge, kindIcons, memoryTitle, SectionHeading } from '../../components';
import { DecorativeOrb } from '../../components/decorative-orb';
import { MemoryTypePillRail } from '../../components/memory-type-pill-rail';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { iconBadge, radii, spacing, text } from '../../theme';
import type { Palette } from '../../theme';
import type { ExploreData, Memory, ResurfacingUpdate, Space } from '../../types';

function collectionTints(colors: Palette) { return [colors.petal, colors.icyBlue, colors.lavender, colors.greenTint]; }
export function TroveExploreScreen({ memories, spaces, data, updates, loading, onOpenSpaces, onOpenSpace, onCreateSpace, onOpenMonth, onOpenMemory, onSearch, onCreateMemory }:
  { memories: Memory[]; spaces: Space[]; data: ExploreData | null; updates: ResurfacingUpdate[]; loading: boolean; onOpenSpaces: () => void; onOpenSpace: (id: string) => void; onCreateSpace: () => void; onOpenMonth: (month: string, memoryCount: number) => void; onOpenMemory: (memory: Memory) => void; onSearch: (query: string, kind?: string) => void; onCreateMemory: () => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const tints = collectionTints(colors);
  const currentMonth = data?.months?.[0];
  const monthName = currentMonth
    ? new Intl.DateTimeFormat(undefined, { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(currentMonth.month))
    : 'This month';
  const monthKey = currentMonth?.month.slice(0, 7);
  const monthMemories = monthKey ? memories.filter((memory) => new Date(memory.capturedAt).toISOString().slice(0, 7) === monthKey) : [];

  return <>

    {!!updates.length && <View style={styles.exploreSection}>
      <SectionHeading title="Back in focus" style={styles.exploreSectionHeading} />
      <View style={styles.backInFocusPanel}>{updates.map((update) => <Pressable key={update.memory.id} onPress={() => onOpenMemory(update.memory)} style={({ pressed }) => [styles.backInFocusRow, pressed && styles.exploreCardPressed]} accessibilityRole="button" accessibilityLabel={`${memoryTitle(update.memory)}. ${update.reason}`}>
        {update.memory.previewUrl ? <MemoryImage uri={update.memory.previewUrl} style={styles.backInFocusImage} resizeMode="cover" /> : <IconBadge icon={kindIcons[update.memory.kind]} />}
        <View style={styles.backInFocusCopy}><Text numberOfLines={1} style={styles.backInFocusTitle}>{memoryTitle(update.memory)}</Text></View><Ionicons name="chevron-forward" size={15} color={colors.muted} />
      </Pressable>)}</View>
    </View>}

    <View style={styles.exploreSection}>
      <SectionHeading title="Spaces" action="See all" onAction={onOpenSpaces} style={styles.exploreSectionHeading} />
      {loading && !spaces.length ? <View style={styles.exploreLoading}><ActivityIndicator color={colors.blueDeep} /></View>
        : <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator={false} contentContainerStyle={styles.spaceRail}>
          {spaces.slice(0, 4).map((space, index) => <Pressable key={space.id} onPress={() => onOpenSpace(space.id)} style={({ pressed }) => [styles.exploreSpaceCard, pressed && styles.exploreCardPressed]} accessibilityRole="button" accessibilityLabel={`${space.name}, ${space.memoryCount ?? 0} ${space.memoryCount === 1 ? 'memory' : 'memories'}`}>
            <View style={[styles.spaceArtwork, { backgroundColor: space.color || tints[index % tints.length] }]}><Ionicons name="folder-open-outline" size={22} color={colors.foreground} /></View>
            <View style={styles.exploreSpaceCopy}><Text numberOfLines={1} ellipsizeMode="tail" style={styles.exploreSpaceTitle}>{space.name}</Text></View>
          </Pressable>)}
          <Pressable onPress={onCreateSpace} style={({ pressed }) => [styles.newExploreSpace, pressed && styles.exploreCardPressed]} accessibilityRole="button" accessibilityLabel="Create a Space">
            <View style={styles.newSpaceMark}><Ionicons name="add" size={21} color={colors.foreground} /></View><View style={styles.newExploreSpaceCopy}><Text numberOfLines={1} style={styles.exploreSpaceTitle}>New Space</Text></View>
          </Pressable>
        </ScrollView>}
    </View>

    <View style={styles.exploreSection}>
      <SectionHeading title="Browse by type" style={styles.exploreSectionHeading} />
      <MemoryTypePillRail onSelect={(kind) => onSearch('', kind)} />
    </View>

    <View style={styles.exploreSection}>
      <SectionHeading title="A month in your Trove" trailing={<Ionicons name="calendar-clear-outline" size={18} color={colors.muted} />} style={styles.exploreSectionHeading} />
      <Pressable onPress={() => currentMonth ? onOpenMonth(currentMonth.month, currentMonth.memoryCount) : onCreateMemory()} style={({ pressed }) => [styles.monthRecapCard, pressed && styles.exploreCardPressed]} accessibilityRole="button" accessibilityLabel={currentMonth ? `Open ${monthName} recap, ${currentMonth.memoryCount} memories` : 'Create your first memory'}>
        <View style={styles.monthRecapCopy}>
          <Text style={styles.monthRecapTitle}>{currentMonth ? `${currentMonth.memoryCount} ${currentMonth.memoryCount === 1 ? 'memory' : 'memories'} kept` : 'Your month is waiting'}</Text>
          <Text style={styles.monthRecapAction}>{currentMonth ? 'Open recap' : 'Create a memory'} <Ionicons name="arrow-forward" size={12} color={colors.foreground} /></Text>
        </View>
        <MonthArtwork memories={monthMemories.slice(0, 3)} monthName={monthName} />
      </Pressable>
    </View>

  </>;
}

function MonthArtwork({ memories, monthName }: { memories: Memory[]; monthName: string }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const previews = memories.flatMap((memory) => {
    const uri = memory.previewUrl || (memory.localPending ? memory.localAssetUri : null);
    return uri ? [{ id: memory.id, uri }] : [];
  });
  return <View style={styles.monthArtwork}>
    <DecorativeOrb seed={`month-${monthName}`} size={92} color={colors.lavender} /><View style={styles.monthArtworkRing} />
    {previews.length ? previews.slice(0, 2).map((preview, index) => <MemoryImage key={preview.id} uri={preview.uri} style={[styles.monthPhoto, index === 0 ? styles.monthPhotoBack : styles.monthPhotoFront]} resizeMode="cover" />)
      : <View style={styles.monthArtworkIcon}><Ionicons name="calendar-clear-outline" size={24} color={colors.foreground} /></View>}
  </View>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    exploreSection: { marginBottom: spacing.xxxl },
    exploreSectionHeading: { marginBottom: spacing.lg },
    exploreLoading: { minHeight: 90, justifyContent: 'center', alignItems: 'center' },
    spaceRail: { gap: spacing.lg, paddingRight: spacing.xxxl },
    exploreSpaceCard: { width: 158, minHeight: 100, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, borderRadius: radii.lg, backgroundColor: colors.surface },
    exploreCardPressed: { opacity: 0.82, transform: [{ scale: 0.99 }] },
    spaceArtwork: { height: 62, position: 'relative', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
    exploreSpaceCopy: { minWidth: 0, paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.lg },
    exploreSpaceTitle: { color: colors.foreground, ...text.itemTitle },
    newExploreSpace: { width: 142, minHeight: 100, position: 'relative', overflow: 'hidden', alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderStyle: 'dashed', borderColor: colors.border, borderRadius: radii.lg, backgroundColor: colors.surface },
    newExploreSpaceCopy: { maxWidth: '100%', alignItems: 'center', paddingHorizontal: spacing.lg },
    newSpaceMark: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.sm, borderRadius: radii.sm, backgroundColor: colors.skyBlue },
    monthRecapCard: { minHeight: 142, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md, overflow: 'hidden', padding: spacing.xl, borderRadius: radii.xl, backgroundColor: colors.surface },
    monthRecapCopy: { flex: 1, minWidth: 0 },
    monthRecapTitle: { color: colors.foreground, ...text.display },
    monthRecapAction: { marginTop: spacing.lg, color: colors.foreground, fontSize: 10, fontWeight: '600' },
    monthArtwork: { width: 108, height: 122, position: 'relative', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', borderRadius: radii.md, backgroundColor: colors.lavender },
    monthArtworkRing: { width: 70, height: 70, position: 'absolute', bottom: -35, left: -20, borderWidth: 10, borderColor: 'rgba(255,255,255,0.35)', borderRadius: radii.pill },
    monthArtworkIcon: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(48,45,59,0.12)', borderRadius: radii.md, backgroundColor: 'rgba(255,255,255,0.62)' },
    monthPhoto: { position: 'absolute', width: '51%', height: '50%', borderWidth: 3, borderColor: colors.surface, borderRadius: radii.md },
    monthPhotoBack: { left: 6, top: 13, transform: [{ rotate: '-9deg' }] },
    monthPhotoFront: { right: 6, bottom: 13, transform: [{ rotate: '8deg' }] },
    backInFocusPanel: { overflow: 'hidden', paddingHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, backgroundColor: colors.surface },
    backInFocusRow: { minHeight: 55, flexDirection: 'row', alignItems: 'center', gap: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
    backInFocusImage: { width: iconBadge.row, height: iconBadge.row, borderRadius: radii.sm, backgroundColor: colors.lavender },
    backInFocusCopy: { flex: 1, minWidth: 0 },
    backInFocusTitle: { color: colors.foreground, ...text.buttonSmall },
  });
}
