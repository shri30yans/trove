import { Alert, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { isConnectionMessage, normalizeConnectionMessage } from '../api/messages';
import { useTheme } from '../providers/theme-provider';
import { control, iconSize, press } from '../theme';

/** Keep retryable errors quiet until the user asks for details. */
export function ErrorNotice({ error, onRetry }: { error: string; onRetry: () => void }) {
  const { colors } = useTheme();
  const message = normalizeConnectionMessage(error);
  const connection = isConnectionMessage(message);
  const title = connection ? 'Connection unavailable' : 'Could not refresh';
  return <Pressable
    accessibilityRole="button"
    accessibilityLabel={title}
    accessibilityHint="Show error details and retry"
    onPress={() => Alert.alert(title, message, [
      { text: 'Close', style: 'cancel' },
      { text: 'Retry', onPress: onRetry },
    ])}
    style={({ pressed }) => [styles.button, pressed && press.pressed]}
  >
    <Ionicons name={connection ? 'cloud-offline-outline' : 'alert-circle-outline'} size={iconSize.lg} color={connection ? colors.muted : colors.danger} />
  </Pressable>;
}

const styles = StyleSheet.create({
  button: { width: control.default, height: control.default, alignItems: 'center', justifyContent: 'center', alignSelf: 'flex-end' },
});
