import { errorResponseSchema } from './schemas/common';
/** User-facing transport failure messages. The client is the single owner:
 *  it throws these, and stored legacy strings are rewritten to them at the read boundary. */
export const TIMEOUT_MESSAGE = 'Trove did not respond in time. Check your connection and try again.';
export const CONNECTION_MESSAGE = 'Could not connect to Trove.';

const RAW_TRANSPORT_PATTERN = /fetch failed|network request failed|connectexception|failed to connect|connection refused|econnrefused|enotfound|etimedout|socket closed|unable to resolve host|appears to be offline/i;

export function isConnectionMessage(message: string | null | undefined): boolean {
  return message === TIMEOUT_MESSAGE || message === CONNECTION_MESSAGE;
}

/** Rewrite raw platform transport text (persisted before the client normalized its
 *  own errors) to the friendly connection message. Other messages pass through. */
export function normalizeConnectionMessage(message: string): string {
  return RAW_TRANSPORT_PATTERN.test(message) ? CONNECTION_MESSAGE : message;
}

/** Server details stay diagnostic; UI copy is owned by the API adapter. */
export function apiFailureMessage(status: number, code?: string): string {
  switch (code) {
    case 'invalid_credentials': return 'Your account, password, or both were incorrect. Try again or create a new account.';
    case 'email_not_confirmed': return 'This email address is not confirmed yet. Open the confirmation link in your inbox, then tap "I confirmed — sign in" again.';
    case 'invalid_auth_request': return 'Enter a valid email and password.';
    case 'auth_rate_limited': return 'Too many sign-in attempts. Wait a moment and try again.';
    case 'auth_email_unavailable': return 'Trove could not send your confirmation email. Try again in a few minutes.';
    case 'confirmation_rate_limited': return 'Too many confirmation emails. Wait a minute and try again.';
    case 'email_link_expired': return 'This confirmation link has expired. Request a new one below.';
    case 'email_link_invalid': return 'This confirmation link is invalid. Request a new one below.';
    case 'auth_unavailable': return 'Sign-in is temporarily unavailable. Try again shortly.';
    case 'auth_request_rejected': return 'Check your email and password, then try again.';
    case 'auth_provider_error': return 'Trove could not complete sign-in. Try again shortly.';
    case 'password_reset_session_expired': return 'This password reset link has expired. Request a new one.';
    case 'password_update_rejected': return 'Choose a different password and try again.';
    case 'space_name_exists': return 'A Space with that name already exists. Choose another name.';
    case 'invalid_space': case 'space_not_found': return 'That Space is no longer available. Choose another Space.';
    case 'storage_quota_exceeded': return 'Your storage is full. This save is kept on your device until your plan has more space.';
    case 'upload_size_mismatch': case 'invalid_asset': return 'The attachment could not be verified. Choose the file again.';
    case 'invalid_query': return 'Enter a search phrase up to 1,000 characters.';
    case 'embeddings_unavailable': return 'Embedding search is unavailable. Contact the Trove administrator.';
  }
  if (status === 401) return 'Your session has expired. Sign in again.';
  if (status === 403) return 'You do not have permission to do that.';
  if (status === 404) return 'This item is no longer available. Refresh and try again.';
  if (status === 413) return 'This file or save is too large. Choose a smaller file or shorten the note.';
  if (status === 429) return 'Trove is receiving too many requests. Wait a moment and try again.';
  if (status >= 500) return 'Trove could not complete this request. Try again shortly. If it continues, contact the Trove administrator.';
  if (status === 409) return 'This item has changed. Refresh before trying again.';
  if (status === 400 || status === 422) return 'Trove could not accept this save. Check the details and attachments, then try again.';
  return 'Trove could not complete that request. Try again.';
}

export function apiFailureCode(body: unknown): string | undefined {
  const result = errorResponseSchema.safeParse(body);
  return result.success ? result.data.error.code : undefined;
}
