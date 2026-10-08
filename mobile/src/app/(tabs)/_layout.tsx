import { Text, View } from 'react-native';
import { Tabs, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { BottomNavigation } from '../../components/bottom-navigation';
import { useTroveToastContext } from '../../providers/toast-provider';
import { useTheme } from '../../providers/theme-provider';
import { layout, radii, spacing, text } from '../../theme';

export default function TabsLayout() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { toast } = useTroveToastContext();
  return <View style={{ flex: 1, backgroundColor: colors.background }}>
    <Tabs
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: colors.background } }}
      tabBar={({ state, navigation }) => {
        const route = state.routes[state.index]?.name;
        const selected = route === 'index' ? 'home' : route as 'search' | 'explore' | 'profile';
        if (route === 'search') return null;
        return <BottomNavigation
          selected={selected}
          onSelect={(tab) => navigation.navigate(tab === 'home' ? 'index' : tab)}
          onCapture={() => router.push('/capture')}
          bottomInset={insets.bottom}
        />;
      }}
    >
      <Tabs.Screen name="index" />
      <Tabs.Screen name="search" />
      <Tabs.Screen name="explore" />
      <Tabs.Screen name="profile" />
    </Tabs>
    {toast ? <View style={{ position: 'absolute', zIndex: 10, bottom: layout.navBar + insets.bottom, alignSelf: 'center', maxWidth: '90%', paddingHorizontal: spacing.xl, paddingVertical: spacing.lg, borderRadius: radii.lg, backgroundColor: colors.deep }}><Text style={{ color: colors.surface, textAlign: 'center', ...text.caption }}>{toast}</Text></View> : null}
  </View>;
}
