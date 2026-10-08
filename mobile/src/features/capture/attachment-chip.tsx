import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemedStyles, useTheme } from '../../providers/theme-provider';
import { control, iconSize, radii, spacing, text, type Palette } from '../../theme';
import { kindIcons } from '../../components';
import type { CaptureAttachment } from '../../types';

/**
 * Compact attachment chip for the capture composer: thumbnail, title, and a
 * remove control in one pill. Tapping the chip body previews the attachment;
 * the remove control only removes it.
 */
export function AttachmentChip({ attachment, label, disabled = false, onPreview, onRemove }: {
  attachment: CaptureAttachment;
  label?: string;
  disabled?: boolean;
  onPreview: () => void;
  onRemove: () => void;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const title = label || attachment.title || attachment.asset.filename || 'Attachment';
  return (
    <View style={styles.chip}>
      <Pressable disabled={disabled} onPress={onPreview} accessibilityRole="button" accessibilityLabel={`Preview ${title}`} style={styles.body}>
        {attachment.kind === 'image'
          ? <Image source={{ uri: attachment.asset.uri }} style={styles.thumbnail} resizeMode="cover" />
          : <View style={styles.iconWell}><Ionicons name={kindIcons[attachment.kind]} size={iconSize.sm} color={colors.foreground} /></View>}
        <Text numberOfLines={1} style={styles.title}>{title}</Text>
      </Pressable>
      <Pressable disabled={disabled} onPress={onRemove} hitSlop={spacing.sm} accessibilityRole="button" accessibilityLabel={`Remove ${title}`} style={styles.remove}>
        <Ionicons name="close" size={iconSize.xs} color={colors.muted} />
      </Pressable>
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    chip: { height: control.large, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, backgroundColor: colors.background },
    body: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingLeft: spacing.xs },
    thumbnail: { width: control.compact, height: control.compact, borderRadius: radii.xs, backgroundColor: colors.border },
    iconWell: { width: control.compact, height: control.compact, alignItems: 'center', justifyContent: 'center', borderRadius: radii.xs, backgroundColor: colors.icyBlue },
    title: { maxWidth: 120, color: colors.foreground, ...text.itemTitle },
    remove: { width: control.default, height: control.default, alignItems: 'center', justifyContent: 'center' },
  });
}
