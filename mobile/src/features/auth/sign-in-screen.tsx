import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Button, FormScreen, Notice, TextField } from '../../components';
import { useAuth } from '../../providers/auth-provider';
import { useThemedStyles } from '../../providers/theme-provider';
import { spacing, text, type Palette } from '../../theme';

export function SignInScreen({ restoreError }: { restoreError: string | null }) {
  const { signIn } = useAuth();
  const styles = useThemedStyles(makeStyles);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'info' | 'danger'; body: string } | null>(null);

  async function submit() {
    setMessage(null);
    setBusy(true);
    try {
      await signIn(email, password);
    } catch (error) {
      setMessage({ tone: 'danger', body: error instanceof Error ? error.message : 'Trove could not continue. Check your details and try again.' });
    } finally {
      setBusy(false);
    }
  }

  return <FormScreen contentContainerStyle={styles.content}>
    <View style={styles.heading}>
      <Text style={styles.brand}>Trove</Text>
      <Text style={styles.title}>Sign in to Trove</Text>
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
      <TextField
        value={password}
        onChangeText={setPassword}
        placeholder="Password"
        icon="lock-closed-outline"
        accessibilityLabel="Password"
        secureTextEntry
        autoCapitalize="none"
        textContentType="password"
        autoComplete="password"
        returnKeyType="done"
        onSubmitEditing={() => void submit()}
        editable={!busy}
      />
      <Button
        label="Sign in"
        fills
        size="large"
        loading={busy}
        disabled={!email.trim() || !password}
        onPress={() => void submit()}
      />
    </View>
  </FormScreen>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { flexGrow: 1, justifyContent: 'center', gap: spacing.xxxxl, paddingHorizontal: spacing.xxxxl, paddingVertical: spacing.xxxxl },
    heading: { gap: spacing.md },
    brand: { color: colors.blueDeep, ...text.eyebrow, textTransform: 'uppercase' },
    title: { color: colors.foreground, ...text.page },
    subtitle: { color: colors.muted, ...text.body },
    form: { gap: spacing.lg },
  });
}
