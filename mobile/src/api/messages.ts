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
    case 'invalid_credentials': return 'Email or password is incorrect.';
    case 'invalid_auth_request': return 'Enter a valid email and password.';
    case 'auth_rate_limited': return 'Too many sign-in attempts. Wait a moment and try again.';
    case 'auth_unavailable': return 'Sign-in is temporarily unavailable. Try again shortly.';
    case 'auth_not_configured': return 'Trove sign-in is not configured. Contact the administrator.';
    case 'auth_request_rejected': return 'Check your email and password, then try again.';
    case 'auth_provider_error': return 'Trove could not complete sign-in. Try again shortly.';
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
