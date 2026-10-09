import { useState } from 'react';
import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { Button, FormScreen, Notice, TextField } from '../../components';
import { validateNewPassword } from '../../domain/password';
import { useAuth } from '../../providers/auth-provider';
import { useThemedStyles } from '../../providers/theme-provider';
import { spacing, text, type Palette } from '../../theme';

export function SignInScreen({ restoreError }: { restoreError: string | null }) {
  const { signIn, signUp, requestPasswordReset } = useAuth();
  const styles = useThemedStyles(makeStyles);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [creatingAccount, setCreatingAccount] = useState(false);
  const [resettingPassword, setResettingPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'info' | 'danger'; body: string } | null>(null);

  async function submit() {
    setMessage(null);
    if (creatingAccount) {
      const invalid = validateNewPassword(password);
      if (invalid) {
        setMessage({ tone: 'danger', body: invalid });
        return;
      }
    }
    setBusy(true);
    try {
      if (resettingPassword) {
        await requestPasswordReset(email);
        setMessage({ tone: 'info', body: 'If an account exists for this address, you will receive a password reset link by email.' });
      } else if (creatingAccount) {
        const result = await signUp(email, password);
        if (result === 'email_confirmation_required') {
          router.push({ pathname: '/verify-email', params: { email: email.trim() } });
        }
      } else {
        await signIn(email, password);
      }
    } catch (error) {
      setMessage({ tone: 'danger', body: error instanceof Error ? error.message : 'Trove could not continue. Check your details and try again.' });
    } finally {
      setBusy(false);
    }
  }

  return <FormScreen contentContainerStyle={styles.content}>
    <View style={styles.heading}>
      <Text style={styles.brand}>Trove</Text>
      <Text style={styles.title}>{resettingPassword ? 'Reset your password' : creatingAccount ? 'Create your Trove account' : 'Sign in to Trove'}</Text>
    </View>
    {restoreError && <Notice body={restoreError} tone="danger" />}
    {message && <Notice body={message.body} tone={message.tone} />}
    <View style={styles.form}>
      <TextField
        value={email}
        onChangeText={setEmail}
        placeholder="Email address"
        icon="mail-outline"
        accessibilityLabel="Email address"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        textContentType="emailAddress"
        autoComplete="email"
        returnKeyType="next"
        editable={!busy}
      />
      {!resettingPassword && <TextField
        value={password}
        onChangeText={setPassword}
        placeholder={creatingAccount ? 'Choose a password' : 'Password'}
        icon="lock-closed-outline"
        accessibilityLabel={creatingAccount ? 'Choose a password' : 'Password'}
        secureTextEntry
        revealable
        autoCapitalize="none"
        textContentType={creatingAccount ? 'newPassword' : 'password'}
        autoComplete={creatingAccount ? 'new-password' : 'password'}
        returnKeyType="done"
        onSubmitEditing={() => void submit()}
        editable={!busy}
      />}
      <Button
        label={resettingPassword ? 'Send reset link' : creatingAccount ? 'Create account' : 'Sign in'}
        fills
        size="large"
        loading={busy}
        disabled={!email.trim() || (!resettingPassword && !password)}
        onPress={() => void submit()}
      />
      {resettingPassword ? <Button
        label="Back to sign in"
        variant="quiet"
        disabled={busy}
        onPress={() => { setResettingPassword(false); setPassword(''); setMessage(null); }}
      /> : <View style={styles.links}>
        {creatingAccount ? <Button
          label="Sign in"
          variant="quiet"
          disabled={busy}
          onPress={() => { setCreatingAccount(false); setPassword(''); setMessage(null); }}
        /> : <>
          <Button
            label="Create account"
            variant="quiet"
            disabled={busy}
            onPress={() => { setCreatingAccount(true); setPassword(''); setMessage(null); }}
          />
          <Button
            label="Forgot password?"
            variant="quiet"
            size="compact"
            muted
            disabled={busy}
            onPress={() => { setResettingPassword(true); setPassword(''); setMessage(null); }}
          />
        </>}
      </View>}
    </View>
  </FormScreen>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { flexGrow: 1, justifyContent: 'center', gap: spacing.xxxxl, paddingHorizontal: spacing.xxxxl, paddingVertical: spacing.xxxxl },
    heading: { gap: spacing.md },
    brand: { color: colors.blueDeep, ...text.eyebrow, textTransform: 'uppercase' },
    title: { color: colors.foreground, ...text.page },
    form: { gap: spacing.lg },
    links: { flexDirection: 'row', justifyContent: 'center', gap: spacing.lg },
  });
}
