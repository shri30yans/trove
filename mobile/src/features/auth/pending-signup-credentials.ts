/** Transient credentials for the sign-up → verify-email flow.
 *
 * The verify screen is signed out, so its "I confirmed" check can only ask the
 * server by attempting sign-in with the password the user just registered with.
 * These credentials live in memory only for that single flow: they are never
 * persisted, never logged, only honored for the address they were registered
 * with, and cleared once sign-in succeeds (a newer sign-up overwrites them).
 */
let pending: { email: string; password: string } | null = null;

export function stashPendingSignupCredentials(email: string, password: string) {
  pending = { email: email.trim().toLowerCase(), password };
}

export function peekPendingSignupCredentials(email: string): string | null {
  if (!pending || pending.email !== email.trim().toLowerCase()) return null;
  return pending.password;
}

export function clearPendingSignupCredentials() {
  pending = null;
}
