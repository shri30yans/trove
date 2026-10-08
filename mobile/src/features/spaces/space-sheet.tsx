import { StyleSheet } from 'react-native';
import { Button, Eyebrow, FormScreen, Notice, ScreenHeader, TextField } from '../../components';
import { useKeyboardOnScreenFocus } from '../../hooks/use-keyboard-on-screen-focus';
import { useThemedStyles } from '../../providers/theme-provider';
import { layout, spacing, type Palette } from '../../theme';

export function SpaceSheet({ name, description, onDescription, saving, error, onName, onClose, onSave }: {
  name: string; description: string; onDescription: (value: string) => void; saving: boolean; error: string | null; onName: (value: string) => void; onClose: () => void; onSave: () => void;
}) {
  const styles = useThemedStyles(makeStyles);
  const inputRef = useKeyboardOnScreenFocus();
  return <FormScreen header={<ScreenHeader title="New Space" onBack={saving ? undefined : onClose} />} contentContainerStyle={styles.content}>
        <Eyebrow label="Name" />
        <TextField inputRef={inputRef} value={name} onChangeText={onName} editable={!saving} placeholder="A project or interest" maxLength={80} onSubmitEditing={onSave} returnKeyType="done" accessibilityLabel="Space name" />
        <Eyebrow label="Description" />
        <TextField value={description} onChangeText={onDescription} editable={!saving} placeholder="What belongs in this Space?" multiline maxLength={500} accessibilityLabel="Space description" />
        {error && <Notice title="Could not create Space" body={error} />}
        <Button label="Create Space" size="large" icon="add" loading={saving} disabled={!name.trim()} onPress={onSave} fills />
  </FormScreen>;
}
function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { paddingHorizontal: layout.gutter, paddingBottom: spacing.xxl, gap: spacing.lg },
  });
}
