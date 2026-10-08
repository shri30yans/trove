import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button, Eyebrow, Notice } from '../../components';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { radii, spacing, text, type Palette } from '../../theme';
import { formatLastSynced } from '../../utils/format-last-synced';
import type { SyncStatus } from '../sync/sync-status';
import type { ProcessingSummary } from '../../api/schemas/memories';
import type { EmbeddingState } from '../../domain/embedding-state';
import { processingView } from './processing-view';

const syncIcons: Record<SyncStatus['state'], keyof typeof Ionicons.glyphMap> = {
  loading: 'cloud-outline',
  complete: 'cloud-done-outline',
  uploading: 'cloud-upload-outline',
  offline: 'cloud-offline-outline',
  paused: 'pause-circle-outline',
  retrying: 'cloud-upload-outline',
  blocked: 'alert-circle-outline',
};

const embeddingCopy: Record<Exclude<EmbeddingState['state'], 'error'>, string> = {
  loading: 'Checking embedding search…',
  disabled: 'Off · Search matches the words in your saved content.',
  unavailable: 'On · The embedding service is unavailable right now.',
  available: 'On · Search can match meaning across text and images.',
};

type Props = {
  syncStatus: SyncStatus;
  pendingCount: number;
  syncing: boolean;
  lastSyncedAt: string | null;
  onSyncNow: () => void;
  processingLoading: boolean;
  processingError: string | null;
  processingCounts: ProcessingSummary | null;
  onRetryProcessing: () => void;
  embeddingState: EmbeddingState;
  onRetryEmbeddings: () => void;
};

export function CloudScreen({ syncStatus, pendingCount, syncing, lastSyncedAt, onSyncNow, processingLoading, processingError, processingCounts, onRetryProcessing, embeddingState, onRetryEmbeddings }: Props) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const blocked = syncStatus.state === 'blocked';
  return <>
    <Eyebrow label="Synced" style={styles.sectionLabel} />
    <View style={styles.card}>
      <View style={styles.summaryRow}>
        <View style={[styles.mark, { backgroundColor: blocked ? colors.dangerTint : colors.icyBlue }]}>
          <Ionicons name={syncIcons[syncStatus.state]} size={19} color={blocked ? colors.danger : colors.blueDeep} />
        </View>
        <View style={styles.copy}>
          <Text style={styles.title}>{syncStatus.message}</Text>
          {syncStatus.detail && syncStatus.detail !== syncStatus.message && <Text style={styles.description}>{syncStatus.detail}</Text>}
          <Text style={styles.meta}>{formatLastSynced(lastSyncedAt)}</Text>
        </View>
        {pendingCount > 0 && <Button variant="secondary" size="compact" label={syncing ? 'Syncing…' : blocked ? 'Retry' : 'Sync now'} loading={syncing} disabled={syncStatus.state === 'offline'} onPress={onSyncNow} />}
      </View>
    </View>

    <Eyebrow label="Processed" style={[styles.groupGap, styles.sectionLabel]} />
    <View style={styles.card}>
      {processingLoading && <View style={styles.summaryRow}><ActivityIndicator color={colors.blueDeep} size="small" /></View>}
      {processingError && !processingLoading && <View style={styles.summaryRow}>
        <View style={styles.copy}><Notice body={processingError} tone="danger" /></View>
        <Button variant="secondary" size="compact" label="Retry" onPress={onRetryProcessing} />
      </View>}
      {processingCounts && !processingLoading && !processingError && <ProcessingBlock counts={processingCounts} />}
    </View>

    <Eyebrow label="Embedding search" style={[styles.groupGap, styles.sectionLabel]} />
    <View style={styles.card}>
      {embeddingState.state === 'error'
        ? <View style={styles.summaryRow}><View style={styles.copy}><Notice body={embeddingState.message} tone="danger" /></View><Button variant="secondary" size="compact" label="Retry" onPress={onRetryEmbeddings} /></View>
        : <View style={styles.summaryRow}>
          <View style={[styles.mark, { backgroundColor: embeddingState.state === 'available' ? colors.icyBlue : colors.dangerTint }]}>
            <Ionicons name={embeddingState.state === 'available' ? 'sparkles-outline' : embeddingState.state === 'disabled' ? 'cloud-offline-outline' : 'alert-circle-outline'} size={19} color={embeddingState.state === 'available' ? colors.blueDeep : colors.danger} />
          </View>
          <View style={styles.copy}>
            <Text style={styles.title}>{embeddingCopy[embeddingState.state]}</Text>
            {embeddingState.state !== 'disabled' && <Text style={styles.meta}>Search uses the shared text and image embedding model.</Text>}
          </View>
        </View>}
    </View>
  </>;
}

function ProcessingBlock({ counts }: { counts: ProcessingSummary }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const view = processingView(counts);
  const inProgress = counts.queued + counts.processing;
  const mark = counts.failed > 0
    ? { icon: 'alert-circle-outline' as const, tint: colors.dangerTint, accent: colors.danger }
    : inProgress > 0
      ? { icon: 'hourglass-outline' as const, tint: colors.icyBlue, accent: colors.blueDeep }
      : { icon: 'checkmark-circle-outline' as const, tint: colors.icyBlue, accent: colors.blueDeep };
  return <View>
    <View style={styles.summaryRow}>
      <View style={[styles.mark, { backgroundColor: mark.tint }]}>
        <Ionicons name={mark.icon} size={19} color={mark.accent} />
      </View>
      <View style={styles.copy}>
        <Text style={styles.title}>{view.state === 'empty' ? 'Nothing has reached the cloud yet.' : view.message}</Text>
          <Text style={styles.description}>The server extracts link text and creates embeddings for enabled memories.</Text>
      </View>
    </View>
    {counts.total > 0 && <>
      <View style={styles.statDivider} />
      <View style={styles.statRow}>
        <Stat label="Indexed" value={counts.ready} />
        <Stat label="In progress" value={inProgress} />
        <Stat label="Needs attention" value={counts.failed} danger={counts.failed > 0} />
      </View>
    </>}
  </View>;
}

function Stat({ label, value, danger = false }: { label: string; value: number; danger?: boolean }) {
  const styles = useThemedStyles(makeStyles);
  const { colors } = useTheme();
  return <View style={styles.stat}>
    <Text style={[styles.statValue, danger && { color: colors.danger }]}>{value}</Text>
    <Text style={styles.statLabel}>{label}</Text>
  </View>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    sectionLabel: { marginBottom: spacing.lg },
    groupGap: { marginTop: spacing.xxxxl },
    card: { overflow: 'hidden', borderWidth: 1, borderColor: colors.borderSoft, borderRadius: radii.xl, backgroundColor: colors.surface },
    summaryRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingHorizontal: spacing.xl, minHeight: 68, paddingVertical: spacing.lg },
    mark: { width: 38, height: 38, borderRadius: radii.pill, alignItems: 'center', justifyContent: 'center' },
    copy: { flex: 1, minWidth: 0, gap: spacing.xxs },
    title: { color: colors.foreground, ...text.button },
    description: { color: colors.muted, ...text.caption },
    meta: { color: colors.muted, ...text.meta },
    statDivider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
    statRow: { flexDirection: 'row', paddingHorizontal: spacing.xl, paddingVertical: spacing.lg, gap: spacing.xl },
    stat: { flex: 1, gap: spacing.xxs },
    statValue: { color: colors.foreground, ...text.section },
    statLabel: { color: colors.muted, ...text.meta },
  });
}
