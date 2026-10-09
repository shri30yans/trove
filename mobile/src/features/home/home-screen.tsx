import { MemoryImage } from '../../components/memory-image';
import { useEffect, useState } from 'react';
import { Animated, Easing, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ErrorNotice, IconBadge, LoadMoreButton, MemoryRow, SectionHeading, StatePanel, Wordmark } from '../../components';
import { kindIcons, memoryCountLabel, memoryTitle, shortDate } from '../../utils/memory-metadata';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { collectionTints, iconBadge, layout, radii, screenInsets, spacing, text, type Palette } from '../../theme';
import type { Memory, ResurfacingUpdate, Space } from '../../types';

export function HomeScreen({ memories, spaces, updates, hasMoreMemories, loadingMoreMemories, loading, refreshing, error, onOpenProfile, onOpenMemory, onLoadMore, onSearch, onOpenSpaces, onOpenSpace, onCreateSpace, onRefresh }:
  { memories: Memory[]; spaces: Space[]; updates: ResurfacingUpdate[]; hasMoreMemories: boolean; loadingMoreMemories: boolean; loading: boolean; refreshing: boolean; error: string | null; onOpenProfile: () => void; onOpenMemory: (memory: Memory) => void; onLoadMore: () => void; onSearch: (query: string, kind?: string) => void; onOpenSpaces: () => void; onOpenSpace: (id: string) => void; onCreateSpace: () => void; onRefresh: () => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const tints = collectionTints(colors);
  const [heroSlot] = useState(initialHeroSlot);

  return <FlatList
    style={{ flex: 1, backgroundColor: colors.background }}
    contentContainerStyle={{ ...screenInsets, paddingBottom: layout.navBar + spacing.xxxxl }}
    data={memories}
    keyExtractor={(memory) => memory.id}
    renderItem={({ item }) => <MemoryRow memory={item} onPress={() => onOpenMemory(item)} />}
    refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.blueDeep} />}
    ListHeaderComponent={<>
    <View style={styles.topBar}>
      <Wordmark />
      <View style={styles.topActions}>
        {error && <ErrorNotice error={error} onRetry={onRefresh} />}
        <Pressable onPress={onOpenProfile} accessibilityRole="button" accessibilityLabel="Open profile" style={({ pressed }) => [styles.profileButton, pressed && styles.pressed]}><Ionicons name="person-outline" size={19} color={colors.foreground} /></Pressable>
      </View>
    </View>

    <View style={styles.intro}><HeadlineEntrance text={heroLines[heroSlot % heroLines.length]} /></View>

    <Pressable onPress={() => onSearch('')} style={({ pressed }) => [styles.searchEntry, pressed && styles.searchEntryPressed]} accessibilityRole="button" accessibilityLabel="Search your memories">
      <Ionicons name="search-outline" size={20} color={colors.muted} />
      <Text style={styles.searchHint}>What do you remember?</Text>
    </Pressable>

    <View style={styles.homeSection}>
      <SectionHeading title="Your Spaces" action={spaces.length ? 'See all' : undefined} onAction={onOpenSpaces} style={styles.sectionGap} />
      {spaces.length ? <View style={styles.homeSpaceGrid}>{spaces.slice(0, 2).map((space, index) => <Pressable key={space.id} onPress={() => onOpenSpace(space.id)} style={({ pressed }) => [styles.homeSpaceCard, { backgroundColor: space.color || tints[index % tints.length] }, pressed && styles.pressed]} accessibilityRole="button" accessibilityLabel={`${space.name}, ${memoryCountLabel(space.memoryCount)}`}>
        <View style={styles.homeSpaceTop}><Ionicons name="albums-outline" size={16} color={colors.foreground} /></View>
        <Text numberOfLines={1} style={styles.homeSpaceName}>{space.name}</Text><Text style={styles.homeSpaceCount}>{memoryCountLabel(space.memoryCount)}</Text>
      </Pressable>)}
        <Pressable onPress={onCreateSpace} style={({ pressed }) => [styles.homeSpaceCreate, pressed && styles.pressed]} accessibilityRole="button" accessibilityLabel="Create a Space"><Ionicons name="add" size={19} color={colors.foreground} /><Text style={styles.homeSpaceCreateText}>New Space</Text></Pressable>
      </View> : <Pressable onPress={onCreateSpace} style={({ pressed }) => [styles.firstSpaceCard, pressed && styles.pressed]} accessibilityRole="button" accessibilityLabel="Create a Space"><IconBadge icon="albums-outline" /><View style={{ flex: 1 }}><Text style={styles.firstSpaceTitle}>Start with a Space</Text><Text style={styles.sectionHint}>Projects, interests, plans, or anything you want to keep together.</Text></View><Ionicons name="arrow-forward" size={16} color={colors.foreground} /></Pressable>}
    </View>

    {!!updates.length && <View style={styles.homeSection}>
      <SectionHeading title="Back in focus" trailing={<Ionicons name="sparkles-outline" size={17} color={colors.muted} />} style={styles.sectionGap} />
      {updates.slice(0, 2).map((update) => <Pressable key={update.memory.id} onPress={() => onOpenMemory(update.memory)} style={({ pressed }) => [styles.resurfacingCard, pressed && styles.pressed]} accessibilityRole="button" accessibilityLabel={`${memoryTitle(update.memory)}. ${update.reason}`}>
        {update.memory.previewUrl ? <MemoryImage uri={update.memory.previewUrl} style={styles.resurfacingImage} resizeMode="cover" /> : <IconBadge icon={kindIcons[update.memory.kind]} size="mark" />}
        <View style={styles.resurfacingCopy}><Text numberOfLines={1} style={styles.resurfacingTitle}>{memoryTitle(update.memory)}</Text><Text numberOfLines={2} style={styles.resurfacingReason}>Saved {shortDate(update.memory.capturedAt)} · Connects to {update.relatedTo.title || 'a newer save'}</Text></View>
        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
      </Pressable>)}
    </View>}

    <SectionHeading title="Recent saves" trailing={<Text style={styles.streamCount}>{memories.length}</Text>} style={styles.streamHeader} />
    </>}
    ListEmptyComponent={loading
      ? <StatePanel body="Gathering your memories…" loading />
      : <StatePanel title="Your memory starts here" body="Save a link, image, note, or anything you want to find again. Trove will take it from there." icon="bookmark-outline" />}
    ListFooterComponent={hasMoreMemories ? <LoadMoreButton loading={loadingMoreMemories} onPress={onLoadMore} /> : null}
    />;
}

const heroLines = [
  'Follow the white rabbit.',
  'A place for everything.',
  'Curiouser and curiouser!',
  "I'll be back.",
  'Better late than never.',
  'No place like home.',
  'Well begun is half done.',
  'Slow and steady.',
  'If you build it.',
  'Miles to go.',
  'Promises to keep.',
  'Make your bed.',
  'Hello, 2 a.m. thoughts.',
  'Hello, night owl.',
  'Never lose your towel.',
  'My precious.',
];

const HERO_ROTATE_MS = 30 * 60 * 1000;

const initialHeroSlot = Math.floor(Date.now() / HERO_ROTATE_MS);

function HeadlineEntrance({ text }: { text: string }) {
  const styles = useThemedStyles(makeStyles);
  const [progress] = useState(() => new Animated.Value(0));

  useEffect(() => {
    const animation = Animated.timing(progress, { toValue: 1, duration: 180, easing: Easing.out(Easing.cubic), useNativeDriver: true });
    animation.start();
    return () => animation.stop();
  }, [progress]);
  return <Animated.Text style={[styles.pageTitle, { opacity: progress, transform: [{ translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [4, 0] }) }] }]}>{text}</Animated.Text>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    topBar: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.xxxl },
    topActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.xl },
    profileButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: radii.sheet, backgroundColor: colors.surface },
    intro: { marginBottom: spacing.xxxl },
    pageTitle: { color: colors.foreground, fontSize: 31, fontWeight: '300', letterSpacing: -0.75, lineHeight: 38 },
    searchEntry: { minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, paddingHorizontal: spacing.xxl, borderWidth: 1, borderColor: colors.border, borderRadius: radii.pill, backgroundColor: colors.surface },
    searchEntryPressed: { backgroundColor: colors.surfacePressed, opacity: 0.9 },
    searchHint: { color: colors.muted, ...text.body },
    homeSection: { marginTop: spacing.xxxxl },
    sectionGap: { marginBottom: spacing.xxl },
    sectionHint: { marginTop: spacing.xs, color: colors.muted, ...text.caption },
    homeSpaceGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 8 },
    homeSpaceCard: { width: '48.5%', minHeight: 88, justifyContent: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.lg, borderRadius: radii.md },
    homeSpaceTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 18 },
    homeSpaceName: { marginTop: spacing.md, color: colors.foreground, ...text.itemTitle },
    homeSpaceCount: { marginTop: spacing.xs, color: colors.muted, ...text.meta },
    homeSpaceCreate: { width: '48.5%', minHeight: 88, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, borderWidth: 1, borderStyle: 'dashed', borderColor: colors.border, borderRadius: radii.md, backgroundColor: colors.surface },
    homeSpaceCreateText: { color: colors.foreground, ...text.buttonSmall },
    firstSpaceCard: { minHeight: 76, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, paddingHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, backgroundColor: colors.surface },
    firstSpaceTitle: { color: colors.foreground, ...text.itemTitle },
    resurfacingCard: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, marginBottom: spacing.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, backgroundColor: colors.surface },
    resurfacingImage: { width: iconBadge.mark, height: iconBadge.mark, borderRadius: radii.sm, backgroundColor: colors.lavender },
    resurfacingCopy: { flex: 1, minWidth: 0 },
    resurfacingTitle: { color: colors.foreground, ...text.buttonSmall },
    resurfacingReason: { marginTop: spacing.xs, color: colors.muted, ...text.meta },
    streamHeader: { marginTop: spacing.xxxxl, marginBottom: spacing.md },
    streamCount: { color: colors.muted, ...text.meta },
    pressed: { opacity: 0.78, transform: [{ scale: 0.99 }] },
  });
}
