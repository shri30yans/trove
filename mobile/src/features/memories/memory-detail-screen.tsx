import { MemoryImage } from '../../components/memory-image';
import { useState, type ComponentProps } from 'react';
import {
  ActivityIndicator, Alert, Linking, Pressable, Share, useWindowDimensions,
  StyleSheet, Text, View,
} from 'react-native';
import { downloadMedia } from '../../api/media';
import * as Sharing from 'expo-sharing';
import { Ionicons } from '@expo/vector-icons';
import { ActionSheet, Button, Eyebrow, Notice, IconButton, FormScreen, ScreenFrame, ScreenHeader, Tag, TextField, kindIcons, kindLabels, memoryDescription, memoryTitle } from '../../components';
import { SpreadsheetPreview } from '../../components/spreadsheet-preview';
import { VideoPlayer } from '../../components/video-player';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { layout, spacing, text } from '../../theme';
import type { Palette } from '../../theme';
import { AudioPreview } from './audio-preview';
import type { EmbeddingState } from '../../domain/embedding-state';
import type { Memory, Space } from '../../types';
import { MemoryTagEditor } from './memory-tag-editor';

type MemoryDetailScreenProps = {
  memory: Memory | null; related: Memory[]; spaces: Space[]; loading: boolean; error: string | null; feedbackError: string | null; feedbackPendingId: string | null; embeddingState: EmbeddingState;
  onDelete: (memory: Memory) => Promise<void>;
  onClose: () => void; onSearch: () => void; onSearchTag: (tag: string) => void; onOpenMemory: (memory: Memory) => void; onToggleSpace: (memory: Memory, id: string) => void; onCreateSpace: () => void; onSaveNote: (memory: Memory, note: string) => Promise<boolean>; onSaveTags: (memory: Memory, tags: string[]) => Promise<boolean>; onRelatedFeedback: (id: string, relatedId: string, isRelated: boolean) => void;
};

export function MemoryDetailScreen(props: MemoryDetailScreenProps) {
  return <MemoryDetailContent key={props.memory?.id ?? 'pending'} {...props} />;
}

function MemoryDetailContent({ memory, related, spaces, loading, error, feedbackError, feedbackPendingId, embeddingState, onClose, onSearch, onSearchTag, onDelete, onOpenMemory, onToggleSpace, onCreateSpace, onSaveNote, onSaveTags, onRelatedFeedback }: MemoryDetailScreenProps) {
  const { colors } = useTheme();
  const { height: windowHeight } = useWindowDimensions();
  const styles = useThemedStyles(makeStyles);
  const savedNote = memory?.userNote ?? (memory?.kind === 'text' ? memory.contentText ?? '' : '');
  const [draft, setDraft] = useState({ base: savedNote, value: savedNote });
  const noteDraft = draft.value === draft.base ? savedNote : draft.value;
  const setNoteDraft = (value: string) => setDraft({ base: savedNote, value });
  const noteDirty = noteDraft !== savedNote;
  const [menu, setMenu] = useState<'actions' | 'delete' | 'discard' | 'tags' | 'similar' | 'info' | null>(null);
  const [tagDraft, setTagDraft] = useState<string[]>(memory?.tags ?? []);
  const [tagsSaving, setTagsSaving] = useState(false);
  const [dockExpanded, setDockExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [noteSaving, setNoteSaving] = useState(false);
  const [editingNote, setEditingNote] = useState(false);
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
  const originalUrl = memory.sourceUrl;
  const source = memory.sourceDomain || memory.sourceApp || kindLabels[memory.kind];
  const audioAsset = memory.assets?.find((asset) => asset.mimeType.startsWith('audio/'));
  const videoAsset = memory.assets?.find((asset) => asset.mimeType.startsWith('video/'));
  const imageAsset = memory.assets?.find((asset) => asset.mimeType.startsWith('image/'));
  const spreadsheetAsset = memory.assets?.find((asset) => /spreadsheet|excel|csv|sheet/i.test(`${asset.mimeType} ${asset.filename || ''}`));
  const fileAsset = memory.assets?.find((asset) => asset !== audioAsset && asset !== videoAsset && asset !== imageAsset);
  const mainImage = memory.previewUrl || imageAsset?.url;
  const galleryHeight = Math.max(320, Math.round(windowHeight * 0.86));
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
    try {
      const saved = await onSaveNote(memory, noteDraft);
      if (saved) {
        setDraft({ base: noteDraft.trim(), value: noteDraft.trim() });
        setEditingNote(false);
      }
    } finally {
      setNoteSaving(false);
    }
  };
  const saveTags = async () => {
    if (tagDraft.length > 20 || tagDraft.some((tag) => tag.length > 40)) return;
    setTagsSaving(true);
    try {
      if (await onSaveTags(memory, tagDraft)) {
        setMenu(null);
      }
    } finally { setTagsSaving(false); }
  };
  const closeEditor = () => { if (noteSaving || deleting) return; if (noteDirty) setMenu('discard'); else onClose(); };
  const deleteCurrentMemory = async () => {
    setDeleting(true); setDeleteError(null);
    try { await onDelete(memory); }
    catch (error) { setDeleteError(error instanceof Error ? error.message : 'Could not delete this memory.'); }
    finally { setDeleting(false); }
  };
  return (
    <FormScreen contentContainerStyle={styles.detailContent} footer={<View style={styles.dock}>
      <View style={styles.dockRow}>
        <DockAction icon="sparkles-outline" label="Similar" onPress={() => setMenu('similar')} />
        <DockAction icon="pricetag-outline" label="Tags" onPress={() => { setTagDraft(memory.tags ?? []); setMenu('tags'); }} />
        <DockAction icon="information-circle-outline" label="Info" onPress={() => setMenu('info')} />
        <IconButton icon={dockExpanded ? 'chevron-down' : 'chevron-up'} variant="plain" onPress={() => setDockExpanded((open) => !open)} accessibilityLabel={dockExpanded ? 'Collapse memory actions' : 'Expand memory actions'} />
      </View>
      {dockExpanded && <View style={styles.expandedDock}>
        <Button label="Share" icon="share-outline" variant="quiet" size="compact" onPress={shareMemory} />
        <Button label={editingNote ? 'Editing note' : 'Edit note'} icon="create-outline" variant="quiet" size="compact" disabled={!!memory.localPending} onPress={() => setEditingNote(true)} />
        <Button label="More actions" icon="ellipsis-horizontal" variant="quiet" size="compact" onPress={() => setMenu('actions')} />
      </View>}
    </View>} header={<ScreenHeader title={memoryTitle(memory)} onBack={closeEditor} actions={<><IconButton icon="search-outline" variant="plain" onPress={onSearch} accessibilityLabel="Search memories" /><IconButton icon="ellipsis-horizontal" variant="plain" disabled={noteSaving || deleting} onPress={() => setMenu('actions')} accessibilityLabel="Memory actions" /></>} />}>
        {error && <Notice title="Could not load memory details" body={error} />}
        {memory.localPending && <View style={styles.syncRow}>
          <Ionicons name={memory.localSyncState === 'uploading' ? 'cloud-upload-outline' : 'cloud-offline-outline'} size={15} color={memory.localSyncState === 'blocked' ? colors.danger : colors.muted} />
          <Text style={styles.syncRowText}>{memory.localSyncState === 'uploading' ? 'Uploading' : 'Not uploaded'}</Text>
        </View>}
        {(memory.kind === 'image' || memory.kind === 'link') && mainImage && <View style={[styles.galleryStage, { height: galleryHeight }]}><MemoryImage uri={mainImage} resizeMode="contain" style={[styles.detailImage, { height: galleryHeight }]} accessibilityLabel={memory.kind === 'image' ? 'Saved photo' : 'Link preview'} /></View>}
        {videoAsset && <View style={[styles.galleryStage, { height: galleryHeight }]}><VideoPlayer uri={videoAsset.url} style={[styles.detailVideo, { height: galleryHeight }]} /></View>}
        {audioAsset && <AudioPreview uri={audioAsset.url} />}
        {spreadsheetAsset && <SpreadsheetPreview asset={spreadsheetAsset} onOpenExternally={() => void openMemoryFile()} />}
        {!audioAsset && !videoAsset && !spreadsheetAsset && memory.kind === 'link' && <View style={styles.linkPreview}><View style={styles.linkCopy}><Text style={styles.linkDomain}>{source}</Text><Text numberOfLines={2} style={styles.linkUrl}>{memory.sourceUrl || memoryTitle(memory)}</Text></View>{originalUrl && <Pressable onPress={() => void Linking.openURL(originalUrl)} style={styles.linkOpen} accessibilityRole="button" accessibilityLabel="Open original link"><Ionicons name="arrow-forward" size={18} color={colors.foreground} /></Pressable>}</View>}
        {!mainImage && !audioAsset && !videoAsset && !spreadsheetAsset && memory.kind !== 'link' && memory.kind !== 'text' && <View style={styles.genericPreview}><Ionicons name={kindIcons[memory.kind]} size={25} color={colors.muted} /><Text style={styles.genericPreviewText}>{memory.description || memory.contentText || memoryDescription(memory)}</Text></View>}

        <View style={styles.noteSection}>
          <View style={styles.noteHeader}><Eyebrow label={memory.kind === 'text' ? 'Note' : 'Your note'} />
            {!memory.localPending && <Button label={editingNote ? 'Cancel' : savedNote ? 'Edit' : 'Add note'} variant="quiet" size="compact" disabled={noteSaving || deleting} onPress={() => { if (editingNote) { setDraft({ base: savedNote, value: savedNote }); setEditingNote(false); } else setEditingNote(true); }} />}
          </View>
          {editingNote && !memory.localPending
            ? <><TextField value={noteDraft} onChangeText={setNoteDraft} editable={!noteSaving && !deleting} placeholder="Write a note…" multiline containerStyle={styles.noteInput} accessibilityLabel="Edit memory note" /><View style={styles.noteActions}><Button label="Reset" variant="quiet" size="compact" disabled={!noteDirty || noteSaving} onPress={() => setNoteDraft(savedNote)} /><Button label="Save note" size="compact" disabled={!noteDirty || deleting} loading={noteSaving} onPress={() => void editMemoryNote()} /></View></>
            : <Text style={[styles.noteText, !savedNote && styles.emptyNote]}>{savedNote || 'Add a note to remember why this matters.'}</Text>}
        </View>

        <View style={styles.detailSection}><Text style={styles.detailMuted}>{kindLabels[memory.kind]} · Saved {dateLabel}{source ? ` · ${source}` : ''}</Text></View>
        {!!memory.tags?.length && <View accessibilityLabel="Memory tags" style={styles.tagRail}>{memory.tags.map((tag) => <Pressable key={tag} onPress={() => onSearchTag(tag)} accessibilityRole="button" accessibilityLabel={`Find memories tagged ${tag}`} style={styles.tagButton}><Tag label={tag} icon="pricetag-outline" /></Pressable>)}</View>}

        {!memory.localPending && <View style={styles.detailSection}><View style={styles.detailSectionHeader}><Eyebrow label="Spaces" /></View>
          <View style={styles.spaceList}>{spaces.length ? spaces.map((space) => {
            const selected = savedSpaces.some((saved) => saved.id === space.id);
            return <Pressable key={space.id} onPress={() => onToggleSpace(memory, space.id)} accessibilityRole="button" accessibilityState={{ selected }} accessibilityLabel={`${selected ? 'Remove from' : 'Add to'} ${space.name}`} style={({ pressed }) => [styles.spaceRow, pressed && styles.pressed]}><Ionicons name={selected ? 'checkmark-circle' : 'ellipse-outline'} size={18} color={selected ? colors.blueDeep : colors.muted} /><Text style={styles.spaceName}>{space.name}</Text></Pressable>;
          }) : <Button label="Create a Space" icon="add" variant="quiet" size="compact" onPress={onCreateSpace} />}</View>
        </View>}

        {memory.pageText && <View style={styles.detailSection}><Eyebrow label="Page content" /><Text numberOfLines={8} style={styles.pageText}>{memory.pageText}</Text></View>}

        {fileAsset && !spreadsheetAsset && <View style={styles.detailSection}><Eyebrow label="File" /><Pressable onPress={() => void openMemoryFile()} disabled={openingFile} style={styles.fileAction}><Ionicons name="document-outline" size={20} color={colors.muted} /><View style={styles.fileActionCopy}><Text numberOfLines={1} style={styles.detailActionText}>{fileAsset.filename || 'Open attachment'}</Text><Text style={styles.detailMuted}>{openingFile ? 'Preparing file…' : 'Open in another app'}</Text></View><Ionicons name="open-outline" size={16} color={colors.foreground} /></Pressable></View>}

        {!memory.localPending && <View style={styles.detailSection}><View style={styles.detailSectionHeader}><Eyebrow label={memory.kind === 'image' ? 'Related memories' : 'Related things you saved'} />{loading && <ActivityIndicator color={colors.blueDeep} size="small" />}</View>
          {feedbackError && <Notice body={feedbackError} />}
          {related.length ? related.slice(0, 6).map((item) => <View key={item.id} style={styles.relatedMemoryRow}>
            <Pressable style={styles.relatedMemoryButton} onPress={() => onOpenMemory(item)} accessibilityRole="button" accessibilityLabel={memoryTitle(item)}><Text style={styles.relatedTitle}>{memoryTitle(item)}</Text><Text numberOfLines={2} style={styles.detailMuted}>{memoryDescription(item)}</Text></Pressable>
            <IconButton icon="thumbs-down-outline" size="small" variant="plain" disabled={feedbackPendingId !== null} onPress={() => onRelatedFeedback(memory.id, item.id, false)} accessibilityLabel="Not related" />
          </View>) : <Text style={styles.detailMuted}>{embeddingState.state === 'available' ? 'Related memories will appear here as you save more.' : embeddingState.state === 'disabled' ? 'Related memories are off for this account.' : 'Related memories are unavailable right now.'}</Text>}
        </View>}

      {menu && <ActionSheet title={menu === 'delete' ? 'Delete memory?' : menu === 'discard' ? 'Unsaved changes' : menu === 'tags' ? 'Add or edit tags' : menu === 'similar' ? 'Similar memories' : menu === 'info' ? 'Memory details' : 'Memory actions'} onClose={() => setMenu(null)} busy={deleting || tagsSaving}>
        {menu === 'actions' ? <>
          <Button label="Add or edit tags" icon="pricetag-outline" variant="secondary" fills disabled={!!memory.localPending} onPress={() => { setTagDraft(memory.tags ?? []); setMenu('tags'); }} />
          <Button label="Share memory" icon="share-outline" variant="secondary" fills onPress={() => { setMenu(null); shareMemory(); }} />
          <Button label="Delete memory" icon="trash-outline" variant="danger" fills disabled={!!memory.localPending} onPress={() => { setDeleteError(null); setMenu('delete'); }} />
        </> : menu === 'tags' ? <>
          <Text style={styles.detailMuted}>Choose a tag you already use or create a new one. Tags stay private to your account.</Text>
          <MemoryTagEditor tags={tagDraft} onChange={setTagDraft} disabled={tagsSaving} />
          <Button label="Save tags" fills loading={tagsSaving} disabled={tagDraft.length > 20 || tagDraft.some((tag) => tag.length > 40)} onPress={() => void saveTags()} />
        </> : menu === 'similar' ? <>
          {feedbackError && <Notice body={feedbackError} />}
          {related.length ? related.slice(0, 8).map((item) => <Pressable key={item.id} style={styles.relatedMemoryButton} onPress={() => { setMenu(null); onOpenMemory(item); }} accessibilityRole="button" accessibilityLabel={`Open similar memory ${memoryTitle(item)}`}><Text style={styles.relatedTitle}>{memoryTitle(item)}</Text><Text numberOfLines={2} style={styles.detailMuted}>{memoryDescription(item)}</Text></Pressable>) : <Text style={styles.detailMuted}>{embeddingState.state === 'available' ? 'Similar memories will appear here as your library grows.' : 'Similar memory search is unavailable right now.'}</Text>}
        </> : menu === 'info' ? <>
          <Text style={styles.infoLabel}>Type</Text><Text style={styles.infoValue}>{kindLabels[memory.kind]}</Text>
          <Text style={styles.infoLabel}>Saved</Text><Text style={styles.infoValue}>{dateLabel}</Text>
          {!!source && <><Text style={styles.infoLabel}>Source</Text><Text style={styles.infoValue}>{source}</Text></>}
          {!!memory.tags?.length && <><Text style={styles.infoLabel}>Tags</Text><Text style={styles.infoValue}>{memory.tags.join(' · ')}</Text></>}
        </> : menu === 'delete' ? <>
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
    </FormScreen>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    dock: { paddingTop: spacing.sm, paddingBottom: spacing.xs, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, backgroundColor: colors.surface },
    dockRow: { minHeight: 46, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
    dockAction: { minWidth: 62, minHeight: 44, alignItems: 'center', justifyContent: 'center', gap: spacing.xs },
    dockLabel: { color: colors.secondary, ...text.caption, fontWeight: '600' },
    expandedDock: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: spacing.sm, paddingTop: spacing.sm, paddingBottom: spacing.xs },
    galleryStage: { marginHorizontal: -layout.gutter, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background },
    syncRow: { minHeight: 38, flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md },
    syncRowText: { flex: 1, color: colors.muted, ...text.meta },
    detailContent: { flexGrow: 1, paddingHorizontal: layout.gutter, paddingBottom: spacing.xxxxl },
    detailImage: { width: '100%', backgroundColor: colors.background },
    detailVideo: { width: '100%', backgroundColor: colors.background },
    detailActionText: { flex: 1, minWidth: 0, color: colors.foreground, ...text.button },
    detailSection: { marginTop: spacing.xxxl },
    tagRail: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md },
    tagButton: { minHeight: 44, justifyContent: 'center' },
    infoLabel: { marginTop: spacing.lg, color: colors.muted, ...text.caption, textTransform: 'uppercase' },
    infoValue: { marginTop: spacing.xs, color: colors.foreground, ...text.reading },
    noteSection: { marginTop: spacing.xxxl },
    noteHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    noteText: { marginTop: spacing.md, color: colors.foreground, ...text.reading },
    emptyNote: { color: colors.muted },
    detailSectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    spaceList: { marginTop: spacing.sm },
    spaceRow: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    spaceName: { color: colors.foreground, ...text.body },
    pressed: { opacity: 0.8 },
    detailMuted: { marginTop: spacing.md, color: colors.muted, fontSize: 12, lineHeight: 18 },
    relatedMemoryRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
    relatedMemoryButton: { flex: 1, minHeight: 64, justifyContent: 'center', paddingVertical: spacing.sm },
    relatedTitle: { color: colors.foreground, ...text.itemTitle },
    noteInput: { minHeight: 92, marginTop: spacing.md },
    noteActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: spacing.md, marginTop: spacing.md },
    pageText: { marginTop: spacing.lg, color: colors.secondary, ...text.body },
    linkPreview: { minHeight: 84, flexDirection: 'row', alignItems: 'center', gap: spacing.xl, paddingVertical: spacing.xl },
    linkCopy: { flex: 1, minWidth: 0 },
    linkDomain: { color: colors.foreground, ...text.itemTitle },
    linkUrl: { marginTop: spacing.xs, color: colors.muted, ...text.caption },
    linkOpen: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
    genericPreview: { minHeight: 140, justifyContent: 'center', alignItems: 'center', gap: spacing.lg, paddingVertical: spacing.xxxl },
    genericPreviewText: { color: colors.foreground, textAlign: 'center', ...text.reading },
    fileAction: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, marginTop: spacing.lg },
    fileActionCopy: { flex: 1, minWidth: 0 },
  });
}

function DockAction({ icon, label, onPress }: { icon: ComponentProps<typeof Ionicons>['name']; label: string; onPress: () => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return <Pressable style={styles.dockAction} onPress={onPress} accessibilityRole="button" accessibilityLabel={label}>
    <Ionicons name={icon} size={19} color={colors.foreground} />
    <Text style={styles.dockLabel}>{label}</Text>
  </Pressable>;
}
