import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { KeyboardAvoidingView, KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useThemedStyles } from '../providers/theme-provider';
import { layout, screenInsets, spacing, type Palette } from '../theme';

type ScreenProps = { header?: ReactNode; children: ReactNode };

/** Fixed actions stay in normal layout while the library resizes the viewport. */
export function ScreenFrame({ header, children, footer }: ScreenProps & { footer?: ReactNode }) {
  const themed = useThemedStyles(makeStyles);
  return <KeyboardAvoidingView automaticOffset behavior="padding" style={themed.screen}>
    <ScreenChrome header={header} footer={footer}>{children}</ScreenChrome>
  </KeyboardAvoidingView>;
}

/** Forms scroll their focused field into view; no second avoidance wrapper. */
export function FormScreen({ header, children, contentContainerStyle, footer }: ScreenProps & { contentContainerStyle?: StyleProp<ViewStyle>; footer?: ReactNode }) {
  return <ScreenChrome header={header} footer={footer}>
    <KeyboardAwareScrollView keyboardShouldPersistTaps="handled" bottomOffset={spacing.xxl} contentContainerStyle={contentContainerStyle} style={styles.viewport}>
      {children}
    </KeyboardAwareScrollView>
  </ScreenChrome>;
}

function ScreenChrome({ header, children, footer }: ScreenProps & { footer?: ReactNode }) {
  const themed = useThemedStyles(makeStyles);
  return <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={themed.screen}>
    {header && <View style={screenInsets}>{header}</View>}
    <View style={styles.body}>{children}</View>
    {footer && <View style={styles.footer}>{footer}</View>}
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  viewport: { flex: 1 },
  body: { flex: 1, minHeight: 0 },
  footer: { paddingHorizontal: layout.gutter, paddingVertical: spacing.xxl },
});
function makeStyles(colors: Palette) {
  return StyleSheet.create({ screen: { flex: 1, backgroundColor: colors.background } });
}
