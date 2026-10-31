import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useDebounce } from 'use-debounce';
import { getMemoryTags } from '../../api/memories';
import { useTheme, useThemedStyles } from '../../providers/theme-provider';
import { control, press, radii, spacing, text, type Palette } from '../../theme';

export function MemoryTagEditor({ tags, onChange, disabled }: {
  tags: string[]; onChange: (tags: string[]) => void; disabled: boolean;
}) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const [input, setInput] = useState('');
  const value = input.trim().toLowerCase().replace(/^#/, '');
  const [search] = useDebounce(value, 120);
  const tagQuery = useQuery({ queryKey: ['memory-tags', search], queryFn: ({ signal }) => getMemoryTags(search, signal), staleTime: 30_000 });
  const suggestions = tagQuery.data?.tags ?? [];
  const selected = new Set(tags.map((tag) => tag.toLowerCase()));
  const matches = suggestions.filter(({ tag }) => tag.includes(value) && !selected.has(tag)).slice(0, 8);
  const exactMatch = suggestions.find(({ tag }) => tag === value);
  const createValue = value.length > 0 && value.length <= 40 && !selected.has(value) && !exactMatch;

  const add = (tag: string) => {
    const normalized = tag.trim().toLowerCase().replace(/^#/, '');
    if (!normalized || normalized.length > 40 || selected.has(normalized) || tags.length >= 20) return;
    onChange([...tags, normalized]);
    setInput('');
  };
  const remove = (tag: string) => onChange(tags.filter((value) => value !== tag));

  return <View>
    <View style={[styles.inputShell, disabled && styles.disabledShell]}>
      <Ionicons name="pricetag-outline" size={17} color={colors.blueDeep} />
      {tags.map((tag) => <View key={tag} accessibilityLabel={`Tag ${tag}`} style={styles.selectedPill}>
        <Text numberOfLines={1} style={styles.selectedText}>#{tag}</Text>
        <Pressable onPress={() => remove(tag)} disabled={disabled} accessibilityRole="button" accessibilityLabel={`Remove ${tag}`} hitSlop={8} style={styles.removeButton}>
          <Ionicons name="close" size={13} color={colors.secondary} />
        </Pressable>
      </View>)}
      <TextInput
        value={input}
        onChangeText={setInput}
        editable={!disabled && tags.length < 20}
        placeholder={tags.length >= 20 ? '20 tag limit reached' : 'Find or create a tag'}
        placeholderTextColor={colors.muted}
        style={styles.input}
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="done"
        accessibilityRole="combobox"
        accessibilityLabel="Find an existing tag or create a new one"
        accessibilityHint="Type to search tags. Press Done to add an exact match or create the typed tag."
        onSubmitEditing={() => { if (exactMatch) add(exactMatch.tag); else if (createValue) add(value); }}
      />
      {!!input && <Pressable onPress={() => setInput('')} accessibilityRole="button" accessibilityLabel="Clear tag search" hitSlop={8}><Ionicons name="close-circle" size={19} color={colors.muted} /></Pressable>}
    </View>

    {!!tags.length && <View accessibilityLabel={`${tags.length} selected tags`} style={styles.selectedSummary}>
      <Text style={styles.selectedCount}>{tags.length} of 20 tags</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Remove all tags" onPress={() => onChange([])} disabled={disabled} style={styles.clearAll}>
        <Text style={styles.clearText}>Clear</Text>
      </Pressable>
    </View>}

    <View style={styles.suggestionList} accessibilityLabel="Tag suggestions">
      {createValue && <SuggestionRow label={`Create “${value}”`} detail="Add as a new private tag" onPress={() => add(value)} disabled={disabled || tags.length >= 20} styles={styles} colors={colors} create />}
      {matches.map(({ tag, memoryCount }) => <SuggestionRow key={tag} label={`#${tag}`} detail={`${memoryCount} ${memoryCount === 1 ? 'memory' : 'memories'}`} onPress={() => add(tag)} disabled={disabled || tags.length >= 20} styles={styles} colors={colors} />)}
      {tagQuery.isError && <Text accessibilityRole="alert" style={styles.empty}>Couldn’t load tag suggestions. You can still create a new tag.</Text>}
      {tagQuery.isFetching && <Text style={styles.empty}>Finding tags…</Text>}
      {!value && tags.length === 0 && suggestions.length === 0 && !tagQuery.isFetching && <Text style={styles.empty}>Your first tag will be private to your account.</Text>}
      {value.length > 40 && <Text style={styles.empty}>Tags can be up to 40 characters.</Text>}
      {tags.length >= 20 && <Text style={styles.empty}>You can add up to 20 tags to a memory.</Text>}
    </View>
  </View>;

}

function SuggestionRow({ label, detail, onPress, disabled, styles, colors, create = false }: {
  label: string; detail: string; onPress: () => void; disabled: boolean; styles: TagEditorStyles; colors: Palette; create?: boolean;
}) {
  return <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityLabel={`${label}, ${detail}`} style={({ pressed }) => [styles.suggestionRow, pressed && press.rowPressed]}>
    <View style={[styles.suggestionIcon, create && styles.createIcon]}><Ionicons name={create ? 'add' : 'pricetag-outline'} size={17} color={colors.blueDeep} /></View>
    <View style={styles.suggestionCopy}><Text style={styles.suggestionLabel}>{label}</Text><Text style={styles.suggestionDetail}>{detail}</Text></View>
    <Ionicons name="arrow-forward" size={16} color={colors.muted} />
  </Pressable>;
}

type TagEditorStyles = ReturnType<typeof makeStyles>;

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    inputShell: { minHeight: control.large, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: spacing.sm, padding: spacing.sm, borderWidth: 1, borderColor: colors.border, borderRadius: radii.xl, backgroundColor: colors.surface },
    disabledShell: { opacity: 0.65 },
    input: { flexGrow: 1, flexBasis: 120, minWidth: 96, minHeight: 42, paddingHorizontal: spacing.sm, color: colors.foreground, ...text.input },
    selectedSummary: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: spacing.xs },
    selectedCount: { color: colors.muted, ...text.caption },
    selectedPill: { minHeight: 36, maxWidth: '100%', flexDirection: 'row', alignItems: 'center', gap: 2, paddingLeft: spacing.md, paddingRight: spacing.xs, borderWidth: 1, borderColor: colors.border, borderRadius: radii.pill, backgroundColor: colors.icyBlue },
    selectedText: { maxWidth: 160, color: colors.foreground, ...text.buttonSmall },
    removeButton: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center', borderRadius: radii.pill, backgroundColor: colors.surface },
    clearAll: { minHeight: 36, justifyContent: 'center', paddingHorizontal: spacing.sm },
    clearText: { color: colors.secondary, ...text.caption },
    suggestionList: { paddingTop: spacing.sm },
    suggestionRow: { minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingHorizontal: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.borderSoft },
    suggestionIcon: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', borderRadius: radii.md, backgroundColor: colors.icyBlue },
    createIcon: { backgroundColor: colors.greenTint },
    suggestionCopy: { flex: 1, gap: 2 },
    suggestionLabel: { color: colors.foreground, ...text.itemTitle },
    suggestionDetail: { color: colors.muted, ...text.caption },
    empty: { paddingVertical: spacing.md, color: colors.muted, ...text.caption },
  });
}
