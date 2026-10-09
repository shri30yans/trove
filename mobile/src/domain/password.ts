/** The app's password composition rule, owned once and shared by create-account and reset flows. */
export const MIN_PASSWORD_LENGTH = 6;

// One password field with a reveal toggle: seeing the typed value replaces the confirmation field.
export function validateNewPassword(password: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) return 'Use a password with at least 6 characters.';
  return null;
}
