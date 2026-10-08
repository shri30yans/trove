import type { RefObject } from 'react';
import type { StyleProp, TextStyle, ViewStyle, TextInputProps } from 'react-native';
import { StyleSheet, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { IconButton } from './icon-button';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { control, iconSize, radii, spacing, text, type Palette } from '../theme';

type IconName = keyof typeof Ionicons.glyphMap;

/**
 * Every text surface in the app: search, notes, and Space names. Single-line
 * fields share the pill shape and `control` height of the buttons beside them.
 * The input spans the whole field so Android autofill highlights the full pill,
 * with the icon and clear button overlaid rather than displacing it.
 */
export function TextField({
  value, onChangeText, placeholder, icon, size = 'default', multiline = false, onClear, inputRef,
  accessibilityLabel, containerStyle, inputStyle, ...input
}: {
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  icon?: IconName;
  size?: 'compact' | 'default' | 'large';
  multiline?: boolean;
  onClear?: () => void;
  inputRef?: RefObject<TextInput | null>;
  accessibilityLabel?: string;
  containerStyle?: StyleProp<ViewStyle>;
  inputStyle?: StyleProp<TextStyle>;
} & Omit<TextInputProps, 'value' | 'onChangeText' | 'placeholder' | 'multiline'>) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const leadingInset = spacing.xl + (icon ? iconSize.lg + spacing.md : 0);
  const trailingInset = spacing.xl + (onClear ? control.default + spacing.md : 0);
  return (
    <View style={[
      styles.field,
      { minHeight: heights[size], borderRadius: multiline ? radii.lg : radii.pill },
      multiline && styles.fieldMultiline,
      containerStyle,
    ]}>
      <TextInput
        ref={inputRef}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        multiline={multiline}
        accessibilityLabel={accessibilityLabel ?? placeholder}
        style={[styles.input, { paddingLeft: leadingInset, paddingRight: trailingInset }, multiline && styles.inputMultiline, inputStyle]}
        selectionColor={`${colors.blueDeep}55`} // blueDeep is 6-digit hex in every palette; the suffix adds the alpha
        {...input}
      />
      {icon && <View pointerEvents="none" style={styles.iconOverlay}>
        <Ionicons name={icon} size={iconSize.lg} color={colors.muted} />
      </View>}
      {!!value && onClear && <View pointerEvents="box-none" style={styles.clearOverlay}>
        <IconButton icon="close-circle" size="small" variant="plain" onPress={onClear} accessibilityLabel="Clear text" />
      </View>}
    </View>
  );
}

const heights = { compact: control.compact, default: control.default, large: control.large } as const;

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    field: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
    fieldMultiline: { alignSelf: 'stretch', paddingVertical: spacing.lg },
    input: { flex: 1, minWidth: 0, color: colors.foreground, ...text.input },
    inputMultiline: { alignSelf: 'stretch', textAlignVertical: 'top', ...text.compose },
    iconOverlay: { position: 'absolute', left: spacing.xl, top: 0, bottom: 0, justifyContent: 'center' },
    clearOverlay: { position: 'absolute', right: spacing.xl, top: 0, bottom: 0, justifyContent: 'center' },
  });
}
