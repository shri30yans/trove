import { MemoryImage } from '../../components/memory-image';
import { useState } from 'react';
import {
  ActivityIndicator, Alert,  Linking, Modal, Pressable, Share,
  StyleSheet, Text, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { downloadMedia } from '../../api/media';
import * as Sharing from 'expo-sharing';
import { Ionicons } from '@expo/vector-icons';
import { ActionSheet, Button, Eyebrow, Notice, IconBadge, IconButton, FormScreen, ScreenFrame, MemoryRow, Pill, ScreenHeader, TextField, kindIcons, kindLabels, memoryDescription, memoryTitle } from '../../components';
import { SpreadsheetPreview } from '../../components/spreadsheet-preview';
import { VideoPlayer } from '../../components/video-player';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { layout, radii, spacing, text } from '../../theme';
import type { Palette } from '../../theme';
import { AudioPreview } from './audio-preview';
import type { EmbeddingState } from '../../domain/embedding-state';
import type { Memory, Space } from '../../types';

type MemoryDetailSheetProps = {
  memory: Memory | null; related: Memory[]; spaces: Space[]; loading: boolean; error: string | null; feedbackError: string | null; feedbackPendingId: string | null; embeddingState: EmbeddingState;
  onDelete: (memory: Memory) => Promise<void>;
  onClose: () => void; onOpenMemory: (memory: Memory) => void; onToggleSpace: (memory: Memory, id: string) => void; onCreateSpace: () => void; onSaveNote: (memory: Memory, note: string) => Promise<boolean>; onRelatedFeedback: (id: string, relatedId: string, isRelated: boolean) => void;
};

export function MemoryDetailSheet(props: MemoryDetailSheetProps) {
  return <MemoryDetailContent key={props.memory?.id ?? 'pending'} {...props} />;
}

function MemoryDetailContent({ memory, related, spaces, loading, error, feedbackError, feedbackPendingId, embeddingState, onClose, onDelete, onOpenMemory, onToggleSpace, onCreateSpace, onSaveNote, onRelatedFeedback }: MemoryDetailSheetProps) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const savedNote = memory?.userNote ?? (memory?.kind === 'text' ? memory.contentText ?? '' : '');
  const [draft, setDraft] = useState({ base: savedNote, value: savedNote });
  const noteDraft = draft.value === draft.base ? savedNote : draft.value;
  const setNoteDraft = (value: string) => setDraft({ base: savedNote, value });
  const noteDirty = noteDraft !== savedNote;
  const [menu, setMenu] = useState<'delete' | 'discard' | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [noteSaving, setNoteSaving] = useState(false);
  const [imagePreviewOpen, setImagePreviewOpen] = useState(false);
  const [openingFile, setOpeningFile] = useState(false);
  if (!memory || loading) return (
    <ScreenFrame header={<ScreenHeader title="Memory" onBack={onClose} />}>
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xxxxl }}>
        {loading ? <ActivityIndicator color={colors.blueDeep} /> : <Ionicons name="alert-circle-outline" size={25} color={colors.muted} />}
        <Text style={styles.detailMuted}>{loading ? 'Opening this memory…' : error ?? 'This memory could not be found.'}</Text>
      </View>
    </ScreenFrame>
  );
  const savedSpaces = memory.spaces || [];
  const spaceEvidence = new Map<string, { space: NonNullable<Memory['spaces']>[number]; relatedIds: Set<string> }>();
  for (const relatedMemory of related) {
    for (const space of relatedMemory.spaces || []) {
      const evidence = spaceEvidence.get(space.id) || { space, relatedIds: new Set<string>() };
      evidence.relatedIds.add(relatedMemory.id);
      spaceEvidence.set(space.id, evidence);
    }
  }
  const likelySpace = [...spaceEvidence.values()]
    .filter(({ space, relatedIds }) => relatedIds.size >= 2 && !savedSpaces.some((saved) => saved.id === space.id))
    .sort((left, right) => right.relatedIds.size - left.relatedIds.size)[0];
  const originalUrl = memory.sourceUrl;
  const source = memory.sourceDomain || memory.sourceApp || kindLabels[memory.kind];
  const audioAsset = memory.assets?.find((asset) => asset.mimeType.startsWith('audio/'));
  const videoAsset = memory.assets?.find((asset) => asset.mimeType.startsWith('video/'));
  const imageAsset = memory.assets?.find((asset) => asset.mimeType.startsWith('image/'));
  const spreadsheetAsset = memory.assets?.find((asset) => /spreadsheet|excel|csv|sheet/i.test(`${asset.mimeType} ${asset.filename || ''}`));
  const fileAsset = memory.assets?.find((asset) => asset !== audioAsset && asset !== videoAsset && asset !== imageAsset);
  const mainImage = memory.previewUrl || imageAsset?.url;
  const dateLabel = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(memory.capturedAt));
  const shareMemory = () => void Share.share({
    title: memoryTitle(memory),
    message: [memoryTitle(memory), memory.userNote || memory.description || memory.contentText, memory.sourceUrl].filter(Boolean).join('\n\n'),
  });
  const openMemoryFile = async () => {
    if (!fileAsset) return;
    setOpeningFile(true);
    try {
      const filename = `${memory.id}-${fileAsset.filename || 'attachment'}`;
      const uri = await downloadMedia(fileAsset.url, filename, fileAsset.mimeType);
      if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(uri, { mimeType: fileAsset.mimeType, dialogTitle: 'Open memory file' });
      else await Linking.openURL(uri);
    } catch (openError) {
      Alert.alert('File could not be opened', openError instanceof Error ? openError.message : 'Try again in a moment.');
    } finally { setOpeningFile(false); }
  };
  const editMemoryNote = async () => {
    setNoteSaving(true);
    const saved = await onSaveNote(memory, noteDraft);
    setNoteSaving(false);
    if (saved) setDraft({ base: noteDraft.trim(), value: noteDraft.trim() });
  };
  const closeEditor = () => { if (noteSaving || deleting) return; if (noteDirty) setMenu('discard'); else onClose(); };
  const deleteCurrentMemory = async () => {
    setDeleting(true); setDeleteError(null);
    try { await onDelete(memory); }
    catch (error) { setDeleteError(error instanceof Error ? error.message : 'Could not delete this memory.'); }
    finally { setDeleting(false); }
  };
  return (
    <FormScreen contentContainerStyle={styles.detailContent} header={<ScreenHeader title={memoryTitle(memory)} subtitle={`${kindLabels[memory.kind]} · Saved ${dateLabel}`} onBack={closeEditor} actions={<View style={styles.headerActions}><IconButton icon="share-outline" variant="plain" onPress={shareMemory} accessibilityLabel="Share memory" /><IconButton icon="trash-outline" variant="plain" disabled={!!memory.localPending || noteSaving || deleting} onPress={() => { setDeleteError(null); setMenu('delete'); }} accessibilityLabel="Delete memory" /></View>} />}>
        {error && <Notice title="Could not load memory details" body={error} />}
        {memory.localPending && <View style={styles.syncRow}>
          <Ionicons name={memory.localSyncState === 'uploading' ? 'cloud-upload-outline' : 'cloud-offline-outline'} size={15} color={memory.localSyncState === 'blocked' ? colors.danger : colors.muted} />
          <Text style={styles.syncRowText}>{memory.localSyncState === 'uploading' ? 'Uploading' : 'Not uploaded'}</Text>
        </View>}
        {mainImage && memory.kind === 'image' && <Pressable onPress={() => setImagePreviewOpen(true)} accessibilityRole="button" accessibilityLabel="Open photo full screen"><MemoryImage uri={mainImage} resizeMode="cover" style={styles.detailImage} /></Pressable>}
        {videoAsset && <VideoPlayer uri={videoAsset.url} style={styles.detailVideo} />}
        {audioAsset && <AudioPreview uri={audioAsset.url} />}
        {spreadsheetAsset && <SpreadsheetPreview asset={spreadsheetAsset} onOpenExternally={() => void openMemoryFile()} />}
        {memory.kind === 'link' && <View style={styles.linkPreview}><IconBadge icon="link-outline" size="mark" tint={colors.icyBlue} /><View style={styles.linkCopy}><Text style={styles.linkDomain}>{source}</Text><Text numberOfLines={2} style={styles.linkUrl}>{memory.sourceUrl || memoryTitle(memory)}</Text></View>{originalUrl && <Pressable onPress={() => void Linking.openURL(originalUrl)} style={styles.linkOpen} accessibilityRole="button" accessibilityLabel="Open original link"><Ionicons name="arrow-forward" size={18} color={colors.foreground} /></Pressable>}</View>}
        {!mainImage && !audioAsset && !videoAsset && !spreadsheetAsset && memory.kind !== 'link' && (memory.kind !== 'text' || memory.localPending) && <View style={styles.genericPreview}><View style={styles.genericPreviewIcon}><Ionicons name={kindIcons[memory.kind]} size={25} color={colors.foreground} /></View><Text style={styles.genericPreviewText}>{memory.description || memory.contentText || memoryDescription(memory)}</Text></View>}
        {!memory.localPending && <View style={styles.noteSection}>
          <View style={styles.detailSectionHeader}><Eyebrow label={memory.kind === 'text' ? 'Note' : 'Your note'} /></View>
          <TextField value={noteDraft} onChangeText={setNoteDraft} editable={!noteSaving && !deleting} placeholder="Write a note…" multiline containerStyle={styles.noteInput} accessibilityLabel="Edit memory note" />
          <View style={styles.noteActions}><Button label="Reset" variant="quiet" size="compact" disabled={!noteDirty || noteSaving} onPress={() => setNoteDraft(savedNote)} /><Button label="Save" size="compact" disabled={!noteDirty || deleting} loading={noteSaving} onPress={() => void editMemoryNote()} /></View>
        </View>}
        {!memory.localPending && <View style={styles.detailSection}><View style={styles.detailSectionHeader}><Eyebrow label="Spaces" /></View>
          <View style={styles.detailChips}>{spaces.length ? spaces.map((space) => {
            const selected = savedSpaces.some((saved) => saved.id === space.id);
            return <Pill key={space.id} label={space.name} icon={selected ? 'checkmark' : 'add'} maxWidth={190} selected={selected} onPress={() => onToggleSpace(memory, space.id)} accessibilityLabel={`${selected ? 'Remove from' : 'Add to'} ${space.name}`} />;
          }) : <Pill label="Create a Space" icon="add" maxWidth={190} selected={false} onPress={onCreateSpace} />}</View>
        </View>}

        {!memory.localPending && likelySpace && <Pressable onPress={() => onToggleSpace(memory, likelySpace.space.id)} style={({ pressed }) => [styles.spaceSuggestion, pressed && styles.pressed]} accessibilityRole="button" accessibilityLabel={`Add this memory to ${likelySpace.space.name}, suggested by ${likelySpace.relatedIds.size} related saves`}>
          <View style={styles.spaceSuggestionIcon}><Ionicons name="sparkles-outline" size={16} color={colors.foreground} /></View>
          <View style={styles.spaceSuggestionCopy}><Text style={styles.spaceSuggestionTitle}>Likely fits {likelySpace.space.name}</Text><Text style={styles.spaceSuggestionHint}>Based on {likelySpace.relatedIds.size} related saves already in this Space.</Text></View>
          <Text style={styles.spaceSuggestionAction}>Add</Text>
        </Pressable>}


        {memory.pageText && <View style={styles.detailSection}><Eyebrow label="Page content" /><Text numberOfLines={8} style={styles.pageText}>{memory.pageText}</Text></View>}

        {fileAsset && !spreadsheetAsset && <View style={styles.detailSection}><Eyebrow label="File" /><Pressable onPress={() => void openMemoryFile()} disabled={openingFile} style={styles.fileAction}><IconBadge icon="document-outline" tint={colors.icyBlue} /><View style={styles.fileActionCopy}><Text numberOfLines={1} style={styles.detailActionText}>{fileAsset.filename || 'Open attachment'}</Text><Text style={styles.detailMuted}>{openingFile ? 'Preparing file…' : 'Open in another app'}</Text></View><Ionicons name="open-outline" size={16} color={colors.foreground} /></Pressable></View>}

        {!memory.localPending && <View style={styles.detailSection}><View style={styles.detailSectionHeader}><Eyebrow label={memory.kind === 'image' ? 'Similar images & ideas' : 'Related things you saved'} />{loading && <ActivityIndicator color={colors.blueDeep} size="small" />}</View>
          {feedbackError && <Notice body={feedbackError} />}
          {related.length ? related.slice(0, 6).map((item) => <View key={item.id} style={styles.relatedMemoryRow}>
            <View style={styles.relatedMemoryButton}><MemoryRow memory={item} compact onPress={() => onOpenMemory(item)} /></View>
            <IconButton icon="thumbs-down-outline" size="small" variant="plain" disabled={feedbackPendingId !== null} onPress={() => onRelatedFeedback(memory.id, item.id, false)} accessibilityLabel="Not related" />
          </View>) : <Text style={styles.detailMuted}>{embeddingState.state === 'available' ? 'As you save more, Trove can find related ideas and images.' : embeddingState.state === 'disabled' ? 'Embedding search is off for this account.' : 'Related memories are unavailable right now.'}</Text>}
        </View>}
      {menu && <ActionSheet title={menu === 'delete' ? 'Delete memory?' : 'Unsaved changes'} onClose={() => setMenu(null)} busy={deleting}>
        {menu === 'delete' ? <>
          <Text style={styles.detailMuted}>This memory will be removed from your library and Spaces.</Text>
          {deleteError && <Notice body={deleteError} />}
          <Button label="Delete memory" variant="danger" loading={deleting} fills onPress={() => void deleteCurrentMemory()} />
          <Button label="Keep memory" variant="secondary" fills disabled={deleting} onPress={() => setMenu(null)} />
        </> : <>
          <Text style={styles.detailMuted}>Save your changes before leaving, or discard them.</Text>
          <Button label="Keep editing" fills onPress={() => setMenu(null)} />
          <Button label="Discard changes" variant="danger" fills onPress={onClose} />
        </>}
      </ActionSheet>}
      {mainImage && <Modal visible={imagePreviewOpen} animationType="fade" presentationStyle="fullScreen" onRequestClose={() => setImagePreviewOpen(false)}><SafeAreaView style={styles.imagePreviewSafe}><View style={styles.previewHeader}><Text style={styles.previewTitle}>{memoryTitle(memory)}</Text><IconButton icon="close" onPress={() => setImagePreviewOpen(false)} accessibilityLabel="Close photo" /></View><MemoryImage uri={mainImage} resizeMode="contain" style={styles.imagePreview} /></SafeAreaView></Modal>}
    </FormScreen>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    previewHeader: { minHeight: 58, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.xl, paddingHorizontal: spacing.xl, backgroundColor: colors.background },
    previewTitle: { flex: 1, color: colors.foreground, fontSize: 15, fontWeight: '600' },
    headerActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
    syncRow: { minHeight: 38, flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    syncRowText: { flex: 1, color: colors.muted, ...text.meta },
    detailContent: { paddingHorizontal: layout.gutter, paddingBottom: 36 },
    detailImage: { width: '100%', height: 340, borderRadius: radii.xl, backgroundColor: colors.borderSoft },
    detailVideo: { width: '100%', height: 240, borderRadius: radii.lg, backgroundColor: colors.deep },
    detailActionText: { maxWidth: 200, color: colors.foreground, fontSize: 12, fontWeight: '500' },
    detailSection: { marginTop: spacing.xxxl, paddingTop: spacing.xl, borderTopWidth: 1, borderTopColor: colors.border },
    noteSection: { marginTop: spacing.xxl, padding: spacing.xxl, borderRadius: radii.md, backgroundColor: colors.surface },
    detailSectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    detailChips: { flexDirection: 'row', flexWrap: 'wrap', gap: layout.railGap, marginTop: spacing.lg },
    spaceSuggestion: { minHeight: 62, flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: -4, marginBottom: spacing.xl, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, backgroundColor: colors.icyBlue },
    spaceSuggestionIcon: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center', borderRadius: radii.lg, backgroundColor: 'rgba(255,255,255,0.7)' },
    spaceSuggestionCopy: { flex: 1, minWidth: 0 },
    spaceSuggestionTitle: { color: colors.foreground, ...text.buttonSmall },
    spaceSuggestionHint: { marginTop: spacing.xs, color: colors.muted, ...text.meta },
    spaceSuggestionAction: { color: colors.foreground, fontSize: 11, fontWeight: '700' },
    pressed: { opacity: 0.8 },
    detailMuted: { marginTop: spacing.md, color: colors.muted, fontSize: 12, lineHeight: 18 },
    relatedMemoryRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
    relatedMemoryButton: { flex: 1 },
    noteInput: { minHeight: 92, marginTop: spacing.md },
    noteActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: spacing.md, marginTop: spacing.md },
    pageText: { marginTop: spacing.lg, color: colors.secondary, ...text.body },
    linkPreview: { minHeight: 82, flexDirection: 'row', alignItems: 'center', gap: spacing.xl, padding: spacing.xl, borderWidth: 1, borderColor: colors.borderSoft, borderRadius: radii.lg, backgroundColor: colors.surface },
    linkCopy: { flex: 1, minWidth: 0 },
    linkDomain: { color: colors.foreground, ...text.itemTitle },
    linkUrl: { marginTop: spacing.xs, color: colors.muted, ...text.caption },
    linkOpen: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center', borderRadius: radii.lg, backgroundColor: colors.background },
    genericPreview: { minHeight: 138, justifyContent: 'center', alignItems: 'center', gap: spacing.lg, padding: spacing.xxxl, borderRadius: radii.lg, backgroundColor: colors.thistle },
    genericPreviewIcon: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center', borderRadius: radii.md, backgroundColor: 'rgba(255,255,255,0.7)' },
    genericPreviewText: { color: colors.foreground, textAlign: 'center', ...text.body },
    fileAction: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, marginTop: spacing.lg, paddingHorizontal: spacing.xl, borderRadius: radii.md, backgroundColor: colors.surface },
    fileActionCopy: { flex: 1, minWidth: 0 },
    imagePreviewSafe: { flex: 1, backgroundColor: colors.night },
    imagePreview: { flex: 1, width: '100%' },
  });
}
