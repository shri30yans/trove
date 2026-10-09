import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';
import { Button, FormScreen, Notice, Wordmark } from '../../components';
import { useThemedStyles } from '../../providers/theme-provider';
import { spacing, text, type Palette } from '../../theme';

export function AccountDeletionScreen({ deleteAfter, canCancel, onCancel, onCheckStatus }: {
  deleteAfter: string | null;
  canCancel: boolean;
  onCancel: () => Promise<void>;
  onCheckStatus: () => Promise<void>;
}) {
  const styles = useThemedStyles(makeStyles);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deadline = deleteAfter ? new Date(deleteAfter).toLocaleString() : 'soon';

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await action(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Trove could not complete that action. Try again.'); }
    finally { setBusy(false); }
  }

  return <FormScreen contentContainerStyle={styles.content}>
    <Wordmark />
    <Text style={styles.title}>Account deletion scheduled</Text>
    <Text style={styles.body}>{!canCancel
      ? 'Your deletion deadline has passed and Trove is finishing cleanup. Your account remains paused while this completes.'
      : `Your account and cloud memories are scheduled for permanent deletion on ${deadline}. Your account is paused. Cancel before the deadline to keep your account and memories.`}</Text>
    {error && <Notice body={error} tone="danger" />}
    {!canCancel
      ? <Button label="Check deletion status" fills size="large" loading={busy} onPress={() => void run(onCheckStatus)} />
      : <Button label="Cancel deletion and keep my account" fills size="large" loading={busy} onPress={() => void run(onCancel)} />}
  </FormScreen>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { flexGrow: 1, justifyContent: 'center', gap: spacing.xl, paddingHorizontal: spacing.xxxxl, paddingVertical: spacing.xxxxl },
    title: { color: colors.foreground, ...text.page },
    body: { color: colors.muted, ...text.body },
  });
}
