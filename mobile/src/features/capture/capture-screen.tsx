import { useState } from 'react';
import {
  Alert, Image, Linking, Modal, Pressable,
  ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as Sharing from 'expo-sharing';
import { Ionicons } from '@expo/vector-icons';
import { Button, IconBadge, IconButton, ScreenFrame, ScreenHeader, kindIcons } from '../../components';
import { VideoPlayer } from '../../components/video-player';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { useKeyboardOnScreenFocus } from '../../hooks/use-keyboard-on-screen-focus';
import { control, layout, radii, spacing, text, type Palette } from '../../theme';
import { detectCaptureUrl, isVideoUrl, kindFromMimeType } from '../../utils/capture';
import { AttachmentChip } from './attachment-chip';
import { CaptureSpaceSelector } from './capture-space-selector';
import type { CaptureAttachment, MemoryCapture, Space } from '../../types';

export function CaptureScreen({ onClose, onSave, spaceId, spaces }: { onClose: () => void; onSave: (capture: MemoryCapture) => Promise<boolean>; spaceId?: string; spaces: Space[] }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<CaptureAttachment[]>([]);
  const [openMenu, setOpenMenu] = useState<'attachments' | 'spaces' | null>(null);
  const attachmentMenuOpen = openMenu === 'attachments';
  const spaceMenuOpen = openMenu === 'spaces';
  const [spaceOverride, setSpaceOverride] = useState<{ spaceId: string | null } | null>(null);
  const [previewAttachment, setPreviewAttachment] = useState<CaptureAttachment | null>(null);
  const [saving, setSaving] = useState(false);
  const composerRef = useKeyboardOnScreenFocus();

  const save = async () => {
    if (saving) return;
    const content = text.trim();
    if (!content && !attachments.length) return;
    setSaving(true);
    try {
      const sourceUrl = detectCaptureUrl(content) || undefined;
      const urlKind = sourceUrl ? (isVideoUrl(sourceUrl) ? 'video' : 'link') : 'text';
      const primaryAttachment = attachments[0];
      const capture: MemoryCapture = primaryAttachment
        ? {
            kind: primaryAttachment.kind,
            title: primaryAttachment.title,
            sourceApp: primaryAttachment.sourceApp || 'Trove capture',
            captureMetadata: primaryAttachment.captureMetadata,
            attachments,
            sourceUrl,
            userNote: content || undefined,
            contentText: content || undefined,
          }
          : sourceUrl
          ? {
              kind: urlKind,
              sourceUrl,
              userNote: content.replace(sourceUrl, '').trim() || undefined,
              contentText: content,
              sourceApp: 'Trove capture',
              captureMetadata: { capturedInApp: true },
            }
          : {
              kind: 'text',
              title: content.split('\n')[0]?.slice(0, 120),
              userNote: content,
              contentText: content,
              sourceApp: 'Trove note',
            };
      const selectedSpace = spaces.find((space) => space.id === selectedSpaceId);
      const saved = await onSave({ ...capture, spaceIds: selectedSpace ? [selectedSpace.id] : [] });
      if (saved) onClose();
    } finally {
      setSaving(false);
    }
  };

  const addAttachments = (next: CaptureAttachment[]) => {
    if (!next.length) return;
    const remaining = Math.max(0, 20 - attachments.length);
    setAttachments((current) => [...current, ...next.slice(0, Math.max(0, 20 - current.length))]);
    if (next.length > remaining) Alert.alert('Attachment limit reached', 'A memory can include up to 20 attachments.');
  };

  const chooseMedia = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) { Alert.alert('Photo access is off', 'Allow Trove to access your library so you can save a photo or video.'); return; }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images', 'videos'], allowsMultipleSelection: true, selectionLimit: Math.max(1, 20 - attachments.length), quality: 1 });
    if (result.canceled || !result.assets.length) return;
    addAttachments(result.assets.map((asset) => {
      const kind: CaptureAttachment['kind'] = asset.type === 'video' ? 'video' : 'image';
      const mimeType = asset.mimeType || (kind === 'image' ? 'image/jpeg' : 'video/mp4');
      return { kind, title: asset.fileName || (kind === 'image' ? 'Saved image' : 'Saved video'), sourceApp: 'Trove library', asset: { uri: asset.uri, filename: asset.fileName || `${kind}-${Date.now()}.${kind === 'image' ? 'jpg' : 'mp4'}`, mimeType, byteSize: asset.fileSize || undefined }, captureMetadata: { width: asset.width, height: asset.height } };
    }));
    setOpenMenu(null);
  };

  const pickAttachment = async (pick: () => Promise<void>) => {
    try { await pick(); }
    catch { Alert.alert('Could not add attachment', 'Try again. Your draft is still here.'); }
  };

  const chooseCamera = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) { Alert.alert('Camera access is off', 'Allow camera access in your device settings to take a photo.'); return; }
    const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 1 });
    if (result.canceled) return;
    addAttachments(result.assets.map((asset) => ({ kind: 'image', title: asset.fileName || 'Photo', sourceApp: 'Trove camera', asset: { uri: asset.uri, filename: asset.fileName || `photo-${Date.now()}.jpg`, mimeType: asset.mimeType || 'image/jpeg', byteSize: asset.fileSize }, captureMetadata: { width: asset.width, height: asset.height } })));
    setOpenMenu(null);
  };

  const chooseFile = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: '*/*', multiple: true, copyToCacheDirectory: true });
    if (result.canceled || !result.assets.length) return;
    addAttachments(result.assets.map((asset) => {
      const mimeType = asset.mimeType || 'application/octet-stream';
      return { kind: kindFromMimeType(mimeType), title: asset.name, sourceApp: 'Trove files', asset: { uri: asset.uri, filename: asset.name, mimeType, byteSize: asset.size || undefined } };
    }));
    setOpenMenu(null);
  };

  const selectedSpaceId = spaceOverride ? spaceOverride.spaceId : (spaceId ?? null);

  const hasCaptureContent = !!text.trim() || attachments.length > 0;

  return <ScreenFrame header={<ScreenHeader title="New memory" onBack={onClose} />}>
      <ScrollView style={styles.captureViewport} keyboardShouldPersistTaps="always" keyboardDismissMode="none" contentContainerStyle={styles.captureDock}>
        <View testID="capture-composer" style={styles.captureComposer}>
            {!!attachments.length && <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={styles.attachmentGallery} style={styles.attachmentRail} keyboardShouldPersistTaps="handled">
              {attachments.map((attachment, index) => <AttachmentChip
                key={`${attachment.asset.uri}-${index}`}
                attachment={attachment}
                label={attachment.kind === 'image' ? `Photo ${index + 1}` : attachment.kind === 'video' ? `Video ${index + 1}` : undefined}
                disabled={saving}
                onPreview={() => setPreviewAttachment(attachment)}
                onRemove={() => setAttachments((current) => current.filter((_, itemIndex) => itemIndex !== index))}
              />)}
            </ScrollView>}
            <TextInput testID="capture-editor" ref={composerRef} editable={!saving} value={text} onChangeText={setText} placeholder="Write anything you want to remember…" placeholderTextColor={colors.muted} multiline scrollEnabled textAlignVertical="top" style={styles.captureTextArea} accessibilityLabel="Write something to remember" />
            <View style={styles.captureActionBar}>
              <View style={styles.captureDestination}>
              <Pressable accessibilityRole="button" accessibilityLabel={attachmentMenuOpen ? 'Hide attachment options' : 'Add an attachment'} accessibilityState={{ disabled: saving, selected: attachmentMenuOpen, expanded: attachmentMenuOpen }} disabled={saving} hitSlop={spacing.md} onPress={() => setOpenMenu((current) => current === 'attachments' ? null : 'attachments')} style={({ pressed }) => [styles.captureAddButton, pressed && styles.captureAddPressed, saving && styles.captureAddDisabled]}>
                <Ionicons name="add" size={22} color={colors.foreground} />
              </Pressable>
              <CaptureSpaceSelector spaces={spaces} selectedId={selectedSpaceId} expanded={spaceMenuOpen} disabled={saving}
                onToggle={() => setOpenMenu((current) => current === 'spaces' ? null : 'spaces')}
                onSelect={(id) => { setSpaceOverride({ spaceId: id }); setOpenMenu(null); }} />
              </View>
              <IconButton icon="arrow-up-sharp" variant="tinted" selected={hasCaptureContent} disabled={!hasCaptureContent} loading={saving} onPress={() => void save()} accessibilityLabel="Save memory" />
          {attachmentMenuOpen && <View style={styles.captureAddTray}>
            <Button label="Camera" icon="camera-outline" variant="secondary" onPress={() => void pickAttachment(chooseCamera)} />
            <Button label="Photos and videos" icon="images-outline" variant="secondary" onPress={() => void pickAttachment(chooseMedia)} />
            <Button label="Files" icon="document-outline" variant="secondary" onPress={() => void pickAttachment(chooseFile)} />
          </View>}
            </View>
        </View>
      </ScrollView>
    {previewAttachment && <Modal visible animationType="fade" presentationStyle="fullScreen" onRequestClose={() => setPreviewAttachment(null)}>
      <AttachmentPreview attachment={previewAttachment} onClose={() => setPreviewAttachment(null)} />
    </Modal>}
  </ScreenFrame>;
}

function AttachmentPreview({ attachment, onClose }: { attachment: CaptureAttachment; onClose: () => void }) {
  const styles = useThemedStyles(makeStyles);
  const openExternally = async () => {
    try {
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(attachment.asset.uri, { mimeType: attachment.asset.mimeType, dialogTitle: attachment.title || 'Open attachment' });
      } else {
        await Linking.openURL(attachment.asset.uri);
      }
    } catch {
      Alert.alert('Could not open this file', 'Try again from the saved memory.');
    }
  };
  return <SafeAreaView style={styles.previewSafe}>
    <View style={styles.previewHeader}><Text numberOfLines={1} style={styles.previewTitle}>{attachment.title || attachment.asset.filename || 'Attachment'}</Text><IconButton icon="close" onPress={onClose} accessibilityLabel="Close preview" /></View>
    <View style={styles.previewBody}>
      {attachment.kind === 'image' ? <Image source={{ uri: attachment.asset.uri }} style={styles.previewImage} resizeMode="contain" />
        : attachment.kind === 'video' ? <VideoPlayer uri={attachment.asset.uri} style={styles.previewVideo} />
          : <View style={styles.filePreview}><IconBadge icon={kindIcons[attachment.kind]} size="preview" /><Text style={styles.fileName}>{attachment.title || attachment.asset.filename || 'Attachment'}</Text><Text style={styles.fileType}>{attachment.asset.mimeType || 'File'}</Text><Button label="Open file" icon="open-outline" onPress={() => void openExternally()} /></View>}
    </View>
  </SafeAreaView>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    captureViewport: { flex: 1 },
    captureDock: { flexGrow: 1, padding: layout.gutter },
    captureComposer: { flexGrow: 1, padding: spacing.xl, borderWidth: 1, borderColor: colors.border, borderRadius: radii.sheet, backgroundColor: colors.surface },
    captureTextArea: { flex: 1, minHeight: text.compose.lineHeight * 2, paddingHorizontal: spacing.xxs, paddingVertical: spacing.sm, color: colors.foreground, ...text.compose },
    captureActionBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm, marginTop: spacing.sm },
    captureDestination: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    captureAddButton: { width: control.default, height: control.default, alignItems: 'center', justifyContent: 'center', borderRadius: radii.pill, backgroundColor: 'transparent' },
    captureAddPressed: { opacity: 0.72 },
    captureAddDisabled: { opacity: 0.45 },
    captureAddTray: { position: 'absolute', bottom: '100%', left: 0, marginBottom: spacing.md, gap: spacing.md, padding: spacing.lg, borderRadius: radii.sheet, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
    attachmentRail: { flexGrow: 0, flexShrink: 0 },
    attachmentGallery: { gap: spacing.md, paddingBottom: spacing.md },
    previewSafe: { flex: 1, backgroundColor: colors.night },
    previewHeader: { minHeight: control.large, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md, paddingHorizontal: layout.pad, backgroundColor: colors.background },
    previewTitle: { flex: 1, color: colors.foreground, ...text.itemTitle },
    previewBody: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xxl },
    previewImage: { width: '100%', height: '100%' },
    previewVideo: { width: '100%', height: 300 },
    filePreview: { alignItems: 'center', gap: spacing.lg, padding: spacing.xxxl, borderRadius: radii.lg, backgroundColor: colors.background },
    fileName: { maxWidth: 280, color: colors.foreground, ...text.section, textAlign: 'center' },
    fileType: { marginBottom: spacing.sm, color: colors.muted, ...text.subtitle },
  });
}
