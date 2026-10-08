import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useThemedStyles } from '../providers/theme-provider';
import { CreateFab } from './create-fab';
import { Palette, control, layout, radii, shadow, spacing, text } from '../theme';

export type Tab = 'home' | 'search' | 'explore' | 'profile';

const tabs: { key: Tab; label: string }[] = [
  { key: 'home', label: 'Home' },
  { key: 'explore', label: 'Explore' },
  { key: 'search', label: 'Search' },
];

export function BottomNavigation({ selected, onSelect, onCapture, bottomInset }: { selected: Tab; onSelect: (tab: Tab) => void; onCapture: () => void; bottomInset: number }) {
  const styles = useThemedStyles(makeStyles);
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(bottomInset, spacing.md) }]}>
      <View style={styles.dock}>
        {tabs.map((tab) => (
          <Pressable
            key={tab.key}
            onPress={() => onSelect(tab.key)}
            accessibilityRole="tab"
            accessibilityLabel={tab.label}
            accessibilityState={{ selected: selected === tab.key }}
            style={[styles.tab, selected === tab.key && styles.tabSelected]}
          >
            <Text style={[styles.tabLabel, selected === tab.key && styles.tabLabelSelected]}>{tab.label}</Text>
          </Pressable>
        ))}
      </View>
      <CreateFab onPress={onCapture} />
    </View>
  );
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    bar: { position: 'absolute', right: 0, bottom: 0, left: 0, minHeight: layout.navBar, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: spacing.md, paddingHorizontal: layout.gutter, backgroundColor: 'transparent' },
    dock: { width: '65%', maxWidth: 310, flexDirection: 'row', alignItems: 'center', gap: spacing.xxs, padding: spacing.xs, borderRadius: radii.pill, backgroundColor: colors.deep, ...shadow.float },
    tab: { minWidth: 0, height: control.large, flex: 1, alignItems: 'center', justifyContent: 'center', borderRadius: radii.pill },
    tabSelected: { backgroundColor: colors.lavender },
    tabLabel: { color: colors.surface, ...text.buttonSmall },
    tabLabelSelected: { color: colors.foreground },
  });
}
