import { Alert } from 'react-native';
import { useState } from 'react';
import { useRouter } from 'expo-router';
import { AccountSettingsScreen } from '../features/profile/account-settings-screen';
import { useAuth } from '../providers/auth-provider';
import { useGoBack } from '../hooks/use-go-back';

export default function AccountRoute() {
  const router = useRouter();
  const goBack = useGoBack();
  const { signOut, deleteAccount } = useAuth();
  const [operation, setOperation] = useState<'sign_out' | 'delete' | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleSignOut() {
    setError(null);
    setOperation('sign_out');
    void signOut().catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : 'Trove could not sign you out. Try again.');
    }).finally(() => setOperation(null));
  }

  function confirmDeletion() {
    Alert.alert(
      'Schedule account deletion?',
      'Your account and cloud memories will be permanently deleted after a 7-day recovery period. You can cancel before the deadline to keep them.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete account', style: 'destructive', onPress: () => {
          setError(null);
          setOperation('delete');
          void deleteAccount().catch((cause: unknown) => {
            setError(cause instanceof Error ? cause.message : 'Trove could not schedule deletion. Try again.');
          }).finally(() => setOperation(null));
        } },
      ],
    );
  }

  return <AccountSettingsScreen
    signingOut={operation === 'sign_out'}
    deletingAccount={operation === 'delete'}
    error={error}
    onSignOut={handleSignOut}
    onDeleteAccount={confirmDeletion}
    onBack={() => { if (router.canGoBack()) goBack(); else router.replace('/(tabs)/profile'); }}
  />;
}
