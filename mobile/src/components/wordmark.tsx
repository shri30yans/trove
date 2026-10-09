import { Image, StyleSheet, Text, View } from 'react-native';
import { useThemedStyles } from '../providers/theme-provider';
import { spacing } from '../theme';
import type { Palette } from '../theme';

export function Wordmark({ compact = false }: { compact?: boolean }) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.wordmark}>
      <Image
        source={require('../../assets/android-icon-foreground.png')}
        style={styles.brandLogo}
        accessibilityLabel="Trove logo"
        accessible
      />
      {!compact && <Text style={styles.brandName}>Trove</Text>}
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    wordmark: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    brandLogo: { width: 32, height: 32 },
    brandName: { color: colors.foreground, fontSize: 21, fontWeight: '500', letterSpacing: -0.45 },
  });
}
