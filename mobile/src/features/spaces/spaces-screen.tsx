import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DecorativeOrb } from '../../components/decorative-orb';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { radii, spacing, text } from '../../theme';
import type { Palette } from '../../theme';
import type { Space } from '../../types';

type SpacesScreenProps = {
  spaces: Space[];
  defaultCaptureSpaceId: string | null;
  loading: boolean;
  onSelectSpace: (id: string | null) => void;
  onCreateSpace: () => void;
};

export function SpacesScreen({ spaces, defaultCaptureSpaceId, loading, onSelectSpace, onCreateSpace }: SpacesScreenProps) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return <>
    <View style={styles.grid}>
      <CollectionCard label="All saves" detail="Across your library" icon="albums-outline" seed="spaces-grid-all-memories" onPress={() => onSelectSpace(null)} />
      {spaces.map((space, index) => <CollectionCard key={space.id} label={space.name} detail={`${space.memoryCount ?? 0} ${(space.memoryCount ?? 0) === 1 ? 'memory' : 'memories'}`} icon="folder-outline" color={space.color || colors.icyBlue} defaultSpace={space.id === defaultCaptureSpaceId} seed={`space-grid-${space.id}`} placement={index + 1} onPress={() => onSelectSpace(space.id)} />)}
      <Pressable onPress={onCreateSpace} style={({ pressed }) => [styles.newSpaceCard, pressed && styles.pressed]} accessibilityRole="button" accessibilityLabel="Create a space">
        <DecorativeOrb seed="spaces-grid-create" size={118} color="rgba(229,223,236,0.42)" />
        <View style={styles.newSpaceIcon}><Ionicons name="add" size={22} color={colors.foreground} /></View>
        <Text style={styles.cardTitle}>New Space</Text><Text style={styles.cardDetail}>Start a new collection</Text>
      </Pressable>
    </View>
    {!loading && spaces.length === 0 && <View style={styles.emptyHint}><Ionicons name="bulb-outline" size={17} color={colors.foreground} /><Text style={styles.emptyHintText}>Create a Space for a project, interest, or plan. A memory can live in more than one Space.</Text></View>}
  </>;
}

function CollectionCard({ label, detail, icon, color, defaultSpace = false, seed, placement = 0, onPress }: {
  label: string;
  detail: string;
  icon: 'albums-outline' | 'folder-outline';
  color?: string;
  defaultSpace?: boolean;
  seed: string;
  placement?: number;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return <Pressable onPress={onPress} style={({ pressed }) => [styles.collectionCard, pressed && styles.pressed]} accessibilityRole="button" accessibilityLabel={`${label}, ${detail}`}>
    <DecorativeOrb seed={seed} size={126} color="rgba(255,255,255,0.38)" placement={placement} />
    <View style={[styles.collectionIcon, { backgroundColor: color || colors.lavender }]}><Ionicons name={icon} size={19} color={colors.foreground} /></View>
    <Text numberOfLines={1} style={styles.cardTitle}>{label}</Text>
    <Text style={styles.cardDetail}>{detail}</Text>
    {defaultSpace && <View style={styles.defaultBadge}><Ionicons name="flash-outline" size={12} color={colors.foreground} /><Text style={styles.defaultBadgeText}>DEFAULT SPACE</Text></View>}
  </Pressable>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 12 },
    collectionCard: { width: '48.5%', minHeight: 150, position: 'relative', overflow: 'hidden', justifyContent: 'flex-end', paddingHorizontal: spacing.xxl, paddingVertical: spacing.xxl, borderWidth: 1, borderColor: colors.border, borderRadius: radii.sheet, backgroundColor: colors.surface },
    collectionIcon: { width: 39, height: 39, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.xl, borderRadius: radii.sm },
    cardTitle: { paddingRight: spacing.xl, color: colors.foreground, ...text.itemTitle },
    cardDetail: { marginTop: spacing.sm, color: colors.muted, ...text.caption },
    defaultBadge: { position: 'absolute', top: 10, left: 10, flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: radii.md, backgroundColor: 'rgba(255,255,255,0.8)' },
    defaultBadgeText: { color: colors.foreground, ...text.caption },
    newSpaceCard: { width: '48.5%', minHeight: 150, position: 'relative', overflow: 'hidden', alignItems: 'flex-start', justifyContent: 'flex-end', paddingHorizontal: spacing.xxl, paddingVertical: spacing.xxl, borderWidth: 1, borderStyle: 'dashed', borderColor: colors.muted, borderRadius: radii.sheet, backgroundColor: colors.surface },
    newSpaceIcon: { width: 39, height: 39, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.xl, borderRadius: radii.sm, backgroundColor: colors.skyBlue },
    emptyHint: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md, marginTop: spacing.xxl, padding: spacing.xl, borderRadius: radii.sm, backgroundColor: colors.thistle },
    emptyHintText: { flex: 1, color: colors.muted, ...text.caption },
    pressed: { opacity: 0.78, transform: [{ scale: 0.99 }] },
  });
}
