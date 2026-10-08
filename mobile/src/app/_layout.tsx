import { useEffect } from 'react';
import { ActivityIndicator, Platform, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SystemUI from 'expo-system-ui';
import { NavigationBar } from 'expo-navigation-bar';
import { KeyboardProvider } from 'react-native-keyboard-controller';
import { Stack } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { TroveProvider } from '../providers/trove-provider';
import { ThemeProvider, useTheme } from '../providers/theme-provider';
import { AuthProvider, useAuth } from '../providers/auth-provider';
import { SignInScreen } from '../features/auth/sign-in-screen';
import { AccountDeletionScreen } from '../features/auth/account-deletion-screen';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <KeyboardProvider>
        <ThemeProvider>
          <AuthProvider>
            <RootContent />
          </AuthProvider>
        </ThemeProvider>
      </KeyboardProvider>
    </SafeAreaProvider>
  );
}

function RootContent() {
  const { status, restoreError, deletionAt, deletionCancellable, cancelDeletion, checkDeletionStatus } = useAuth();
  const { colors } = useTheme();
  if (status === 'restoring') {
    return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background }}><ActivityIndicator color={colors.blueDeep} /></View>;
  }
  if (status === 'signed_out' || status === 'error') return <SignInScreen restoreError={restoreError} />;
  if (status === 'deletion_pending') return <AccountDeletionScreen deleteAfter={deletionAt} canCancel={deletionCancellable} onCancel={cancelDeletion} onCheckStatus={checkDeletionStatus} />;
  return <TroveProvider><RootStack /></TroveProvider>;
}

function RootStack() {
  const { colors, darkMode } = useTheme();
  useEffect(() => {
    void SystemUI.setBackgroundColorAsync(colors.background).catch(() => {
      console.warn('[Trove appearance]', { stage: 'system-background-failed' });
    });
  }, [colors.background]);
  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <StatusBar style={darkMode ? 'light' : 'dark'} />
      {Platform.OS === 'android' && <NavigationBar style={darkMode ? 'light' : 'dark'} />}
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background } }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="month" options={{ animation: 'slide_from_right' }} />
        <Stack.Screen name="spaces" options={{ animation: 'slide_from_right' }} />
        <Stack.Screen name="space/[id]" options={{ animation: 'slide_from_right' }} />
        <Stack.Screen
          name="capture"
          options={{
            presentation: 'fullScreenModal',
            animation: 'slide_from_bottom',
            animationDuration: 220,
            gestureEnabled: true,
            contentStyle: { backgroundColor: colors.background },
          }}
        />
        <Stack.Screen name="space/new" options={{ presentation: 'fullScreenModal', animation: 'slide_from_bottom' }} />
        <Stack.Screen name="memory/[id]" options={{ presentation: 'fullScreenModal', animation: 'slide_from_bottom', gestureEnabled: false }} />
      </Stack>
    </View>
  );
}
