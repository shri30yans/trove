import type { ReactNode } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useThemedStyles } from '../providers/theme-provider';
import { layout, radii, spacing, text, type Palette } from '../theme';
import { IconButton } from './icon-button';

/** Shared themed surface for actions and their confirmations. */
export function ActionSheet({ title, onClose, children, busy = false }: {
  title: string; onClose: () => void; children: ReactNode; busy?: boolean;
}) {
  const styles = useThemedStyles(makeStyles);
  const insets = useSafeAreaInsets();
  return <Modal transparent animationType="fade" onRequestClose={() => { if (!busy) onClose(); }}>
    <View style={styles.backdrop}>
      <Pressable style={StyleSheet.absoluteFill} onPress={onClose} disabled={busy} accessibilityRole="button" accessibilityLabel="Close options" />
      <View accessibilityViewIsModal style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, spacing.xxl) + spacing.md }]}>
        <View style={styles.header}><Text style={styles.title}>{title}</Text><IconButton icon="close" onPress={onClose} disabled={busy} accessibilityLabel="Close options" /></View>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>{children}</ScrollView>
      </View>
    </View>
  </Modal>;
}
function makeStyles(colors: Palette) {
  return StyleSheet.create({
    backdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: colors.scrim },
    sheet: { maxHeight: '80%', paddingHorizontal: layout.gutter, paddingTop: spacing.xxl, borderTopLeftRadius: radii.sheet, borderTopRightRadius: radii.sheet, backgroundColor: colors.surface },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.lg, marginBottom: spacing.lg },
    title: { flex: 1, color: colors.foreground, ...text.display },
    content: { gap: spacing.lg },
  });
}
