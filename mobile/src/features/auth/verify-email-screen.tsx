import { useEffect, useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { Button, FormScreen, Notice } from '../../components';
import { useAuth } from '../../providers/auth-provider';
import { useThemedStyles } from '../../providers/theme-provider';
import { spacing, text, type Palette } from '../../theme';

const RESEND_COOLDOWN_SECONDS = 60;

export function VerifyEmailScreen() {
  const { email } = useLocalSearchParams<{ email?: string }>();
  const address = typeof email === 'string' ? email : '';
  const { resendConfirmation } = useAuth();
  const styles = useThemedStyles(makeStyles);
  const [busy, setBusy] = useState(false);
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

  return <FormScreen contentContainerStyle={styles.content}>
    <View style={styles.heading}>
      <Text style={styles.brand}>Trove</Text>
      <Text style={styles.title}>Check your email</Text>
    </View>
    <Text style={styles.help}>
      {address
        ? `We sent a confirmation link to ${address}. Tap Confirm email address in that message — Trove will open again to finish. Check spam if you don't see it.`
        : 'We sent a confirmation link to your address. Tap Confirm email address in that message — Trove will open again to finish.'}
    </Text>
    {notice && <Notice body={notice.body} tone={notice.tone} />}
    <View style={styles.form}>
      <Button
        label={cooldown > 0 ? `Resend in ${cooldown}s` : "Didn't get it? Resend"}
        fills
        size="large"
        loading={busy}
        disabled={busy || cooldown > 0 || !address}
        onPress={() => void resend()}
      />
      <Button label="Return to sign in" variant="quiet" disabled={busy} onPress={() => router.replace('/')} />
    </View>
  </FormScreen>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { flexGrow: 1, justifyContent: 'center', gap: spacing.xxxxl, paddingHorizontal: spacing.xxxxl, paddingVertical: spacing.xxxxl },
    heading: { gap: spacing.md },
    brand: { color: colors.blueDeep, ...text.eyebrow, textTransform: 'uppercase' },
    title: { color: colors.foreground, ...text.page },
    help: { color: colors.muted, ...text.body },
    form: { gap: spacing.lg },
  });
}
