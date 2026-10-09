import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { acceptEmailConfirmationSession, acceptPasswordRecoveryUrl, cancelAccountDeletionFromTrove, clearStoredAuthSession, confirmEmailWithToken as confirmEmailWithTokenFromTrove, deleteAccountFromTrove, getAccountDeletionStatus, hasSavedSession, requestPasswordReset as requestPasswordResetFromTrove, resendConfirmationEmail, setSessionExpiredHandler, signInWithPassword, signOutFromTrove, signUpWithPassword, updatePassword as updatePasswordInTrove } from '../api/client';
import { deleteLocalCaptures } from '../features/sync/delete-local-captures';
import { clearAccountLocalPreferences } from '../storage/local-preferences';

type AuthContextValue = {
  status: 'restoring' | 'signed_in' | 'deletion_pending' | 'signed_out' | 'error';
  restoreError: string | null;
  deletionAt: string | null;
  deletionCancellable: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<'authenticated' | 'email_confirmation_required'>;
  requestPasswordReset: (email: string) => Promise<void>;
  resendConfirmation: (email: string) => Promise<void>;
  acceptEmailConfirmation: (session: { accessToken: string; refreshToken: string; expiresIn: number }) => Promise<void>;
  confirmEmailWithToken: (tokenHash: string) => Promise<'email_confirmed' | 'authenticated'>;
  beginPasswordRecovery: (url: string) => Promise<void>;
  completePasswordReset: (password: string) => Promise<void>;
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
  const authRevision = useRef(0);

  const checkDeletionStatus = useCallback(async () => {
    const revision = authRevision.current;
    const deletion = await getAccountDeletionStatus();
    if (revision !== authRevision.current) return;
    if (deletion.deletionComplete) {
      await deleteLocalCaptures();
      await clearAccountLocalPreferences();
      await clearStoredAuthSession();
      if (revision !== authRevision.current) return;
    }
    setDeletionAt(deletion.deleteAfter);
    setDeletionCancellable(deletion.deletionCancellable);
    setStatus(deletion.deletionComplete ? 'signed_out' : deletion.deletionScheduled ? 'deletion_pending' : 'signed_in');
  }, []);

  useEffect(() => {
    let mounted = true;
    const revision = authRevision.current;
    setSessionExpiredHandler(() => { if (mounted) setStatus('signed_out'); });
    void hasSavedSession().then(async (saved) => {
      if (!mounted || revision !== authRevision.current) return;
      if (!saved) {
        setStatus('signed_out');
        return;
      }
      await checkDeletionStatus();
    }).catch((error: unknown) => {
      if (mounted && revision === authRevision.current) {
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
    authRevision.current += 1;
    await signInWithPassword(email, password);
    await checkDeletionStatus();
    setRestoreError(null);
  }, [checkDeletionStatus]);

  const signUp = useCallback(async (email: string, password: string) => {
    authRevision.current += 1;
    const result = await signUpWithPassword(email, password);
    if (result === 'authenticated') {
      await checkDeletionStatus();
      setRestoreError(null);
    }
    return result;
  }, [checkDeletionStatus]);

  const requestPasswordReset = useCallback(async (email: string) => {
    await requestPasswordResetFromTrove(email);
  }, []);

  const resendConfirmation = useCallback(async (email: string) => {
    await resendConfirmationEmail(email);
  }, []);

  const acceptEmailConfirmation = useCallback(async (session: { accessToken: string; refreshToken: string; expiresIn: number }) => {
    authRevision.current += 1;
    await acceptEmailConfirmationSession({ ...session, tokenType: 'Bearer' });
    await checkDeletionStatus();
    setRestoreError(null);
  }, [checkDeletionStatus]);

  const confirmEmailWithToken = useCallback(async (tokenHash: string) => {
    authRevision.current += 1;
    const result = await confirmEmailWithTokenFromTrove(tokenHash);
    if (result.status === 'authenticated') {
      await checkDeletionStatus();
      setRestoreError(null);
    }
    return result.status;
  }, [checkDeletionStatus]);

  const beginPasswordRecovery = useCallback(async (url: string) => {
    await acceptPasswordRecoveryUrl(url);
  }, []);

  const completePasswordReset = useCallback(async (password: string) => {
    authRevision.current += 1;
    await updatePasswordInTrove(password);
    await clearStoredAuthSession();
    setDeletionAt(null);
    setDeletionCancellable(false);
    setStatus('signed_out');
  }, []);

  const signOut = useCallback(async () => {
    authRevision.current += 1;
    await signOutFromTrove();
    setDeletionAt(null);
    setDeletionCancellable(false);
    setStatus('signed_out');
  }, []);

  const deleteAccount = useCallback(async () => {
    authRevision.current += 1;
    const deletion = await deleteAccountFromTrove();
    setDeletionAt(deletion.deleteAfter);
    setDeletionCancellable(deletion.deletionCancellable);
    setStatus('deletion_pending');
  }, []);

  const cancelDeletion = useCallback(async () => {
    authRevision.current += 1;
    await cancelAccountDeletionFromTrove();
    setDeletionAt(null);
    setDeletionCancellable(false);
    setStatus('signed_in');
  }, []);

  const value = useMemo(() => ({ status, restoreError, deletionAt, deletionCancellable, signIn, signUp, requestPasswordReset, resendConfirmation, acceptEmailConfirmation, confirmEmailWithToken, beginPasswordRecovery, completePasswordReset, signOut, deleteAccount, cancelDeletion, checkDeletionStatus }), [status, restoreError, deletionAt, deletionCancellable, signIn, signUp, requestPasswordReset, resendConfirmation, acceptEmailConfirmation, confirmEmailWithToken, beginPasswordRecovery, completePasswordReset, signOut, deleteAccount, cancelDeletion, checkDeletionStatus]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider.');
  return value;
}
