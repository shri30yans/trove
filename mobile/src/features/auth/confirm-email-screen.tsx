import { useEffect, useMemo, useState } from 'react';
import { router } from 'expo-router';
import * as Linking from 'expo-linking';
import { StyleSheet, Text, View } from 'react-native';
import { Button, FormScreen, Notice, TextField } from '../../components';
import { confirmEmailWithToken } from '../../api/client';
import { parseConfirmationLink } from './confirmation-link';
import { useAuth } from '../../providers/auth-provider';
import { useThemedStyles } from '../../providers/theme-provider';
import { spacing, text, type Palette } from '../../theme';

type VerificationResult =
  | { url: string; status: 'confirmed' }
  | { url: string; status: 'failed'; message: string };

export function ConfirmEmailScreen() {
  const url = Linking.useURL();
  const confirmationLink = useMemo(() => (url ? parseConfirmationLink(url) : null), [url]);
  const { resendConfirmation } = useAuth();
  const styles = useThemedStyles(makeStyles);
  // Supabase verifies ConfirmationURL links before redirecting here. Its error query/fragment must
  // take precedence; only an error-free callback counts as provider confirmation.
  const [verificationResult, setVerificationResult] = useState<VerificationResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);

  useEffect(() => {
    if (!url || confirmationLink?.kind !== 'token') return;
    let active = true;
    void confirmEmailWithToken(confirmationLink.tokenHash).then(() => {
      if (active) setVerificationResult({ url, status: 'confirmed' });
    }).catch((error: unknown) => {
      if (active) {
        setVerificationResult({
          url,
          status: 'failed',
          message: error instanceof Error ? error.message : 'This confirmation link is invalid. Request a new one below.',
        });
      }
    });
    return () => { active = false; };
  }, [confirmationLink, url]);

  async function resend() {
    setMessage(null);
    setResent(false);
    if (!email.trim()) {
      setMessage('Enter the email address you signed up with.');
      return;
    }
    setResending(true);
    try {
      await resendConfirmation(email);
      setResent(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Trove could not resend the email. Try again shortly.');
    } finally {
      setResending(false);
    }
  }

  const resultForCurrentUrl = url && verificationResult?.url === url ? verificationResult : null;
  const confirmed = confirmationLink?.kind === 'confirmed' || resultForCurrentUrl?.status === 'confirmed';
  const failed = confirmationLink?.kind === 'failed' || resultForCurrentUrl?.status === 'failed';
  const confirmationMessage = confirmationLink?.kind === 'failed'
    ? confirmationLink.message
    : resultForCurrentUrl?.status === 'failed' ? resultForCurrentUrl.message : null;
  const checking = confirmationLink?.kind === 'token' && resultForCurrentUrl === null;

  if (!url) {
    return <FormScreen contentContainerStyle={styles.content}>
      <View style={styles.heading}>
        <Text style={styles.brand}>Trove</Text>
        <Text style={styles.title}>Confirm your email</Text>
      </View>
      <Notice body="Open the confirmation link from your email to finish setting up your account." tone="info" />
      <Button label="Return to sign in" fills size="large" onPress={() => router.replace('/')} />
    </FormScreen>;
  }

  return <FormScreen contentContainerStyle={styles.content}>
    <View style={styles.heading}>
      <Text style={styles.brand}>Trove</Text>
      <Text style={styles.title}>
        {confirmed ? 'Email confirmed' : failed ? 'Confirmation link unavailable' : 'Confirming your email'}
      </Text>
    </View>
    {!confirmed && checking && <Notice body="Checking your confirmation link…" tone="info" />}
    {confirmed && <>
      <Notice body="Your email is confirmed. Sign in with your password to start using Trove." tone="info" />
      <Button label="Continue to sign in" fills size="large" onPress={() => router.replace('/')} />
    </>}
    {failed && !confirmed && <>
      {confirmationMessage && <Notice body={confirmationMessage} tone="danger" />}
      {message && <Notice body={message} tone="danger" />}
      {resent && <Notice body="New confirmation email sent. Check your inbox and spam folder." tone="info" />}
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
          returnKeyType="done"
          onSubmitEditing={() => void resend()}
          editable={!resending}
        />
        <Button label="Send new link" fills size="large" loading={resending} disabled={!email.trim()} onPress={() => void resend()} />
        <Button label="Return to sign in" variant="quiet" disabled={resending} onPress={() => router.replace('/')} />
      </View>
    </>}
  </FormScreen>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { flexGrow: 1, justifyContent: 'center', gap: spacing.xxxxl, paddingHorizontal: spacing.xxxxl, paddingVertical: spacing.xxxxl },
    heading: { gap: spacing.md },
    brand: { color: colors.blueDeep, ...text.eyebrow, textTransform: 'uppercase' },
    title: { color: colors.foreground, ...text.page },
    form: { gap: spacing.lg },
  });
}
