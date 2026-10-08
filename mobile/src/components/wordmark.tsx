import { StyleSheet, Text, View } from 'react-native';
import { useThemedStyles } from '../providers/theme-provider';
import { spacing } from '../theme';
import type { Palette } from '../theme';

export function Wordmark({ compact = false }: { compact?: boolean }) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={styles.wordmark}>
      <View style={styles.brandMark}><Text style={styles.brandMarkText}>t</Text></View>
      {!compact && <Text style={styles.brandName}>Trove</Text>}
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    wordmark: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    brandMark: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center', borderWidth: 1.4, borderColor: colors.foreground, borderTopLeftRadius: 9, borderTopRightRadius: 9, borderBottomRightRadius: 9, borderBottomLeftRadius: 3 },
    brandMarkText: { color: colors.foreground, fontSize: 17, fontWeight: '500', lineHeight: 20 },
    brandName: { color: colors.foreground, fontSize: 21, fontWeight: '500', letterSpacing: -0.45 },
  });
}
