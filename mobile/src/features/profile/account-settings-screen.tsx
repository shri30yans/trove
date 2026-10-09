import { StyleSheet, Text, View } from 'react-native';
import { Button, Eyebrow, Notice, ScreenFrame, ScreenHeader } from '../../components';
import { useThemedStyles } from '../../providers/theme-provider';
import { spacing, text, type Palette } from '../../theme';

export function AccountSettingsScreen({ signingOut, deletingAccount, error, onSignOut, onDeleteAccount, onBack }: {
  signingOut: boolean;
  deletingAccount: boolean;
  error: string | null;
  onSignOut: () => void;
  onDeleteAccount: () => void;
  onBack: () => void;
}) {
  const styles = useThemedStyles(makeStyles);
  return <ScreenFrame header={<ScreenHeader title="Account" onBack={onBack} />}>
    <View style={styles.content}>
      {error && <Notice body={error} tone="danger" />}
      <View style={styles.signOutSection}>
        <Eyebrow label="Session" />
        <Text style={styles.description}>Sign out of Trove on this device. Your saved account data will remain intact.</Text>
        <Button label="Sign out" icon="log-out-outline" variant="secondary" loading={signingOut} disabled={deletingAccount} onPress={onSignOut} style={styles.signOutButton} />
      </View>

      <View style={styles.dangerZone}>
        <Eyebrow label="Danger zone" style={styles.dangerLabel} />
        <Text style={styles.title}>Delete account</Text>
        <Text style={styles.description}>Your account and cloud memories will be permanently deleted after a 7-day recovery period. You can cancel before then.</Text>
        <Button label="Delete account" icon="trash-outline" variant="danger" loading={deletingAccount} disabled={signingOut} onPress={onDeleteAccount} style={styles.deleteButton} />
      </View>
    </View>
  </ScreenFrame>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    content: { flex: 1, paddingHorizontal: spacing.xxxl, paddingTop: spacing.xl, paddingBottom: spacing.xxxxl, gap: spacing.xxxxl },
    signOutSection: { gap: spacing.md },
    description: { color: colors.muted, ...text.body },
    signOutButton: { alignSelf: 'flex-start', marginTop: spacing.md },
    dangerZone: { gap: spacing.md, marginTop: 'auto', paddingTop: spacing.xxl, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.dangerTint },
    dangerLabel: { color: colors.danger },
    title: { color: colors.foreground, ...text.section },
    deleteButton: { alignSelf: 'flex-start', marginTop: spacing.md },
  });
}
