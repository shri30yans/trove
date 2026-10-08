import { Pressable, StyleSheet, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { Palette, press, radii, shadow, spacing, text } from '../theme';

const fabSize = 78;

export function CreateFab({ onPress, accessibilityLabel = 'Create a memory' }: { onPress: () => void; accessibilityLabel?: string }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      style={({ pressed }) => [styles.fab, pressed && press.pressed]}
    >
      <Ionicons name="add" size={26} color={colors.onAction} />
      <Text style={styles.label}>Create</Text>
    </Pressable>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    fab: { width: fabSize, height: fabSize, alignItems: 'center', justifyContent: 'center', borderRadius: radii.pill, backgroundColor: colors.action, ...shadow.float },
    label: { marginTop: -spacing.xs, color: colors.onAction, ...text.buttonSmall },
  });
}
