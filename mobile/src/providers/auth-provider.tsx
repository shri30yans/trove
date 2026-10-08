import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { cancelAccountDeletionFromTrove, clearStoredAuthSession, deleteAccountFromTrove, getAccountDeletionStatus, hasSavedSession, setSessionExpiredHandler, signInWithPassword, signOutFromTrove } from '../api/client';
import { deleteLocalCaptures } from '../features/sync/delete-local-captures';
import { clearAccountLocalPreferences } from '../storage/local-preferences';

type AuthContextValue = {
  status: 'restoring' | 'signed_in' | 'deletion_pending' | 'signed_out' | 'error';
  restoreError: string | null;
  deletionAt: string | null;
  deletionCancellable: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  deleteAccount: () => Promise<void>;
  cancelDeletion: () => Promise<void>;
  checkDeletionStatus: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthContextValue['status']>('restoring');
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [deletionAt, setDeletionAt] = useState<string | null>(null);
  const [deletionCancellable, setDeletionCancellable] = useState(false);

  const checkDeletionStatus = useCallback(async () => {
    const deletion = await getAccountDeletionStatus();
    if (deletion.deletionComplete) {
      await deleteLocalCaptures();
      await clearAccountLocalPreferences();
      await clearStoredAuthSession();
    }
    setDeletionAt(deletion.deleteAfter);
    setDeletionCancellable(deletion.deletionCancellable);
    setStatus(deletion.deletionComplete ? 'signed_out' : deletion.deletionScheduled ? 'deletion_pending' : 'signed_in');
  }, []);

  useEffect(() => {
    let mounted = true;
    setSessionExpiredHandler(() => { if (mounted) setStatus('signed_out'); });
    void hasSavedSession().then(async (saved) => {
      if (!saved) {
        if (mounted) setStatus('signed_out');
        return;
      }
      if (mounted) await checkDeletionStatus();
    }).catch((error: unknown) => {
      if (mounted) {
        setRestoreError(error instanceof Error ? error.message : 'Could not restore your saved session.');
        setStatus('error');
      }
    });
    return () => {
      mounted = false;
      setSessionExpiredHandler(null);
    };
  }, [checkDeletionStatus]);

  const signIn = useCallback(async (email: string, password: string) => {
    await signInWithPassword(email, password);
    await checkDeletionStatus();
    setRestoreError(null);
  }, [checkDeletionStatus]);

  const signOut = useCallback(async () => {
    await signOutFromTrove();
    setDeletionAt(null);
    setDeletionCancellable(false);
    setStatus('signed_out');
  }, []);

  const deleteAccount = useCallback(async () => {
    const deletion = await deleteAccountFromTrove();
    setDeletionAt(deletion.deleteAfter);
    setDeletionCancellable(deletion.deletionCancellable);
    setStatus('deletion_pending');
  }, []);

  const cancelDeletion = useCallback(async () => {
    await cancelAccountDeletionFromTrove();
    setDeletionAt(null);
    setDeletionCancellable(false);
    setStatus('signed_in');
  }, []);

  const value = useMemo(() => ({ status, restoreError, deletionAt, deletionCancellable, signIn, signOut, deleteAccount, cancelDeletion, checkDeletionStatus }), [status, restoreError, deletionAt, deletionCancellable, signIn, signOut, deleteAccount, cancelDeletion, checkDeletionStatus]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider.');
  return value;
}
