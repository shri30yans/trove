import { useEffect, useState } from 'react';
import { router } from 'expo-router';
import * as Linking from 'expo-linking';
import { StyleSheet, Text, View } from 'react-native';
import { Button, FormScreen, Notice, TextField, Wordmark } from '../../components';
import { MIN_PASSWORD_LENGTH, validateNewPassword } from '../../domain/password';
import { useAuth } from '../../providers/auth-provider';
import { useThemedStyles } from '../../providers/theme-provider';
import { spacing, text, type Palette } from '../../theme';

type LinkState = 'ready' | 'invalid';

export function ResetPasswordScreen() {
  const url = Linking.useURL();
  const { beginPasswordRecovery, completePasswordReset } = useAuth();
  const styles = useThemedStyles(makeStyles);
  const [linkState, setLinkState] = useState<LinkState | null>(null);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!url) return () => { active = false; };
    void beginPasswordRecovery(url).then(() => {
      if (active) setLinkState('ready');
    }).catch((error: unknown) => {
      if (active) {
        setMessage(error instanceof Error ? error.message : 'This password reset link is invalid. Request a new one.');
        setLinkState('invalid');
      }
    });
    return () => { active = false; };
  }, [url, beginPasswordRecovery]);

  async function submit() {
    setMessage(null);
    const invalid = validateNewPassword(password);
    if (invalid) {
      setMessage(invalid);
      return;
    }
    setBusy(true);
    try {
      await completePasswordReset(password);
      setComplete(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Trove could not update your password. Request a new reset link and try again.');
    } finally {
      setBusy(false);
    }
  }

  return <FormScreen contentContainerStyle={styles.content}>
    <View style={styles.heading}>
      <Wordmark />
      <Text style={styles.title}>{complete ? 'Password updated' : 'Choose a new password'}</Text>
    </View>
    {complete ? <>
      <Notice body="Your password has been updated. Sign in with your new password." tone="info" />
      <Button label="Return to sign in" fills size="large" onPress={() => router.replace('/')} />
    </> : url && linkState === null ? <Notice body="Checking your password reset link…" tone="info" /> : !url || linkState === 'invalid' ? <>
      <Notice body={message ?? 'Open the password reset link from your email, or request a new one.'} tone="danger" />
      <Button label="Return to sign in" fills size="large" onPress={() => router.replace('/')} />
    </> : <>
      <Text style={styles.help}>Choose a new password with at least 6 characters. Tap the eye to check it before updating.</Text>
      {message && <Notice body={message} tone="danger" />}
      <View style={styles.form}>
        <TextField
          value={password}
          onChangeText={setPassword}
          placeholder="New password"
          icon="lock-closed-outline"
          accessibilityLabel="New password"
          secureTextEntry
          revealable
          autoCapitalize="none"
          textContentType="newPassword"
          autoComplete="new-password"
          returnKeyType="done"
          onSubmitEditing={() => void submit()}
          editable={!busy}
        />
        <Button label="Update password" fills size="large" loading={busy} disabled={password.length < MIN_PASSWORD_LENGTH} onPress={() => void submit()} />
      </View>
    </>}
  </FormScreen>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { flexGrow: 1, justifyContent: 'center', gap: spacing.xxxxl, paddingHorizontal: spacing.xxxxl, paddingVertical: spacing.xxxxl },
    heading: { gap: spacing.md },
    title: { color: colors.foreground, ...text.page },
    help: { color: colors.muted, ...text.body },
    form: { gap: spacing.lg },
  });
}
