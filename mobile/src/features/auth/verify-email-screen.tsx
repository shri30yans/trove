import { useEffect, useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { Button, FormScreen, Notice, Wordmark } from '../../components';
import { clearPendingSignupCredentials, peekPendingSignupCredentials } from './pending-signup-credentials';
import { useAuth } from '../../providers/auth-provider';
import { useThemedStyles } from '../../providers/theme-provider';
import { spacing, text, type Palette } from '../../theme';

const RESEND_COOLDOWN_SECONDS = 60;

export function VerifyEmailScreen() {
  const { email } = useLocalSearchParams<{ email?: string }>();
  const address = typeof email === 'string' ? email : '';
  const { resendConfirmation, signIn } = useAuth();
  const styles = useThemedStyles(makeStyles);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [notice, setNotice] = useState<{ tone: 'info' | 'danger'; body: string } | null>(null);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown((remaining) => Math.max(0, remaining - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  async function resend() {
    if (!address) {
      setNotice({ tone: 'danger', body: 'Enter your email on the sign-in screen, then create your account again to get a fresh link.' });
      return;
    }
    setNotice(null);
    setBusy(true);
    try {
      await resendConfirmation(address);
      setCooldown(RESEND_COOLDOWN_SECONDS);
      setNotice({ tone: 'info', body: `Confirmation email sent to ${address}. Check your inbox and spam folder.` });
    } catch (error) {
      setNotice({ tone: 'danger', body: error instanceof Error ? error.message : 'Trove could not resend the email. Try again shortly.' });
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    // The screen is signed out, so the only exact confirmation check is a
    // sign-in attempt with the just-registered password. Awaiting it keeps the
    // user here on "not confirmed yet" instead of sending them to sign in.
    setNotice(null);
    const password = address ? peekPendingSignupCredentials(address) : null;
    if (!password) {
      router.replace({ pathname: '/', params: { email: address, emailConfirmed: 'true' } });
      return;
    }
    setConfirming(true);
    try {
      await signIn(address, password);
      clearPendingSignupCredentials();
      router.replace({ pathname: '/' });
    } catch (error) {
      setNotice({ tone: 'danger', body: error instanceof Error ? error.message : 'Trove could not check that yet. Try again shortly.' });
    } finally {
      setConfirming(false);
    }
  }

  return <FormScreen contentContainerStyle={styles.content}>
    <View style={styles.heading}>
      <Wordmark />
      <Text style={styles.title}>Check your email</Text>
    </View>
    <Text style={styles.help}>
      {address
        ? `We sent a confirmation link to ${address}. Tap the link to verify your account. Check spam if you don't see it.`
        : 'We sent a confirmation link to your address. Tap the link to verify your account.'}
    </Text>
    {notice && <Notice body={notice.body} tone={notice.tone} />}
    <View style={styles.form}>
      <Button
        label="I confirmed — sign in"
        fills
        size="large"
        loading={confirming}
        disabled={busy || confirming}
        onPress={() => void confirm()}
      />
      <Button
        label={cooldown > 0 ? `Resend in ${cooldown}s` : "Didn't get it? Resend"}
        variant="quiet"
        size="compact"
        loading={busy}
        disabled={busy || confirming || cooldown > 0 || !address}
        style={styles.resend}
        onPress={() => void resend()}
      />
    </View>
  </FormScreen>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { flexGrow: 1, justifyContent: 'center', gap: spacing.xxxxl, paddingHorizontal: spacing.xxxxl, paddingVertical: spacing.xxxxl },
    heading: { gap: spacing.md },
    title: { color: colors.foreground, ...text.page },
    help: { color: colors.muted, ...text.caption },
    form: { gap: spacing.lg },
    resend: { alignSelf: 'center' },
  });
}
