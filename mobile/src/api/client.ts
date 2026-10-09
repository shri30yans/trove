import type { z } from 'zod';
import { z as zod } from 'zod';
import { readSessionValue, writeSessionValue } from './session-store';
import { parseContract, parseRequest } from './schemas/common';
import {
  authCredentialsSchema,
  authSessionSchema,
  accountDeletionRequestSchema,
  accountDeletionStatusSchema,
  signedInResponseSchema,
  signUpResponseSchema,
  passwordResetResponseSchema,
  passwordUpdateResponseSchema,
  resendConfirmationResponseSchema,
  confirmEmailResponseSchema,
  storedAuthSessionSchema,
} from './schemas/auth';
import { CONNECTION_MESSAGE, apiFailureMessage, apiFailureCode } from './messages';
import { getApiUrl } from './config';
export { getApiUrl } from './config';

const SESSION_KEY = 'trove.auth-session.v1';
const LEGACY_TOKEN_KEY = 'trove.access-token.v1';
type AuthSession = z.infer<typeof storedAuthSessionSchema>;
type SessionResponse = z.infer<typeof authSessionSchema>;
let session: AuthSession | null = null;
let sessionLoaded = false;
let sessionFlight: Promise<string> | null = null;
let onSessionExpired: (() => void) | null = null;

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly code?: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchJson(url: string, init: RequestInit): Promise<{ response: Response; body: unknown }> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error(init.signal?.aborted ? 'Request cancelled.' : CONNECTION_MESSAGE);
  }
  let body: unknown;
  if (response.status !== 204) {
    try { body = await response.json(); }
    catch {
      if (init.signal?.aborted) throw new Error('Request cancelled.');
      if (response.ok) throw new Error('Trove returned an unreadable response.');
    }
  }
  return { response, body };
}

async function loadStoredSession() {
  if (sessionLoaded) return session;
  const encoded = await readSessionValue(SESSION_KEY);
  if (encoded) {
    session = parseContract(storedAuthSessionSchema, JSON.parse(encoded));
    sessionLoaded = true;
    return session;
  }
  const legacyToken = await readSessionValue(LEGACY_TOKEN_KEY);
  session = legacyToken ? { accessToken: legacyToken, refreshToken: null, expiresAt: null } : null;
  sessionLoaded = true;
  return session;
}

async function saveSession(next: AuthSession) {
  await writeSessionValue(SESSION_KEY, JSON.stringify(next));
  await writeSessionValue(LEGACY_TOKEN_KEY, null);
  session = next;
  sessionLoaded = true;
}

async function clearSession() {
  await writeSessionValue(SESSION_KEY, null);
  await writeSessionValue(LEGACY_TOKEN_KEY, null);
  session = null;
  sessionLoaded = true;
}

export async function hasSavedSession() {
  const saved = await loadStoredSession();
  if (!saved) return false;
  if (!saved.refreshToken) {
    await clearSession();
    return false;
  }
  return true;
}

export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler;
}

async function requestUnauthenticated<T>(path: string, schema: z.ZodType<T>, body: unknown) {
  const { response, body: responseBody } = await fetchJson(getApiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const code = apiFailureCode(responseBody);
    throw new ApiError(apiFailureMessage(response.status, code), response.status, code);
  }
  return parseContract(schema, responseBody);
}

function persistProviderSession(next: SessionResponse): Promise<void> {
  return saveSession({
    accessToken: next.accessToken,
    refreshToken: next.refreshToken,
    expiresAt: Date.now() + next.expiresIn * 1000,
  });
}

export async function signInWithPassword(email: string, password: string) {
  const body = parseContract(authCredentialsSchema, { email: email.trim(), password });
  const result = await requestUnauthenticated('/v1/auth/sign-in', signedInResponseSchema, body);
  await persistProviderSession(result.session);
}

export async function signUpWithPassword(email: string, password: string) {
  const body = parseContract(authCredentialsSchema, { email: email.trim(), password });
  const result = await requestUnauthenticated('/v1/auth/sign-up', signUpResponseSchema, body);
  if (result.status === 'authenticated') await persistProviderSession(result.session);
  return result.status;
}

export async function requestPasswordReset(email: string) {
  const body = parseContract(zod.strictObject({ email: zod.email() }), { email: email.trim() });
  return requestUnauthenticated('/v1/auth/password-reset', passwordResetResponseSchema, body);
}

export async function resendConfirmationEmail(email: string) {
  const body = parseContract(zod.strictObject({ email: zod.email() }), { email: email.trim() });
  return requestUnauthenticated('/v1/auth/resend-confirmation', resendConfirmationResponseSchema, body);
}

export async function confirmEmailWithToken(tokenHash: string) {
  const body = parseRequest(zod.strictObject({ token_hash: zod.string().min(1).max(4096) }), { token_hash: tokenHash });
  const result = await requestUnauthenticated('/v1/auth/confirm-email', confirmEmailResponseSchema, body);
  if (result.status === 'authenticated') await persistProviderSession(result.session);
  return result;
}

export async function acceptEmailConfirmationSession(sessionValue: unknown) {
  await persistProviderSession(parseContract(authSessionSchema, sessionValue));
}

export async function acceptPasswordRecoveryUrl(url: string) {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error('This password reset link is invalid. Request a new one.');
  }
  const fragment = new URLSearchParams(parsed.hash.replace(/^#/, ''));
  const get = (key: string) => fragment.get(key) ?? parsed.searchParams.get(key);
  if (parsed.protocol !== 'trove:' || parsed.hostname !== 'reset-password' || get('type') !== 'recovery') {
    throw new Error('This password reset link is invalid. Request a new one.');
  }
  const expiresIn = Number(get('expires_in'));
  const tokenType = get('token_type');
  const authSession = parseContract(authSessionSchema, {
    accessToken: get('access_token'),
    refreshToken: get('refresh_token'),
    tokenType: tokenType?.toLowerCase() === 'bearer' ? 'Bearer' : tokenType,
    expiresIn,
  });
  await persistProviderSession(authSession);
}

export async function updatePassword(password: string) {
  const body = parseRequest(zod.strictObject({ password: zod.string().min(6).max(256) }), { password });
  return request('/v1/auth/password', passwordUpdateResponseSchema, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

async function refreshProviderSession(refreshToken: string) {
  try {
    const result = await requestUnauthenticated(
      '/v1/auth/refresh',
      signedInResponseSchema,
      { refresh_token: refreshToken },
    );
    await persistProviderSession(result.session);
    return result.session.accessToken;
  } catch (error) {
    if (error instanceof ApiError && error.code === 'session_expired') {
      await clearSession();
      onSessionExpired?.();
    }
    throw error;
  }
}

/** Refresh this far ahead of expiry so a request never starts on a token that dies in flight. */
const ACCESS_TOKEN_REFRESH_SKEW_MS = 60_000;

function accessTokenIsUsable(accessToken: string | null | undefined, expiresAt: number | null | undefined) {
  return !!accessToken && Date.now() < (expiresAt ?? Number.POSITIVE_INFINITY) - ACCESS_TOKEN_REFRESH_SKEW_MS;
}

async function loadAccessToken(forceRefresh: boolean) {
  const saved = await loadStoredSession();
  if (!saved?.refreshToken) {
    if (saved) await clearSession();
    throw new ApiError('Sign in to continue.', 401, 'session_missing');
  }
  if (!forceRefresh && accessTokenIsUsable(saved.accessToken, saved.expiresAt)) return saved.accessToken;
  return refreshProviderSession(saved.refreshToken);
}

function accessToken(forceRefresh = false): Promise<string> {
  if (sessionFlight) return sessionFlight;
  if (!forceRefresh && session && accessTokenIsUsable(session.accessToken, session.expiresAt)) {
    return Promise.resolve(session.accessToken);
  }
  sessionFlight = loadAccessToken(forceRefresh).finally(() => { sessionFlight = null; });
  return sessionFlight;
}

export function getAccessToken() {
  return accessToken();
}

export function refreshAccessToken() {
  return accessToken(true);
}

export async function signOutFromTrove() {
  const saved = await loadStoredSession();
  if (!saved?.refreshToken) {
    await clearSession();
    return;
  }
  const token = await accessToken();
  const { response, body } = await fetchJson(getApiUrl('/v1/auth/sign-out'), {
    method: 'POST',
    headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const code = apiFailureCode(body);
    if (code === 'session_expired') {
      await clearSession();
      onSessionExpired?.();
    }
    throw new ApiError(apiFailureMessage(response.status, code), response.status, code);
  }
  await clearSession();
}

export async function getAccountDeletionStatus() {
  const status = await request('/v1/auth/account/deletion', accountDeletionStatusSchema);
  if (status.deletionComplete) await clearSession();
  return status;
}

export async function deleteAccountFromTrove() {
  return request('/v1/auth/account', accountDeletionRequestSchema, { method: 'DELETE' });
}

export async function cancelAccountDeletionFromTrove() {
  await request('/v1/auth/account/deletion/cancel', zod.null(), { method: 'POST' });
}

export async function clearStoredAuthSession() {
  await clearSession();
}

export async function request<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}, retried = false): Promise<T> {
  const token = await accessToken();
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const { response, body } = await fetchJson(getApiUrl(path), { ...init, headers });
  if (response.status === 401 && !retried) {
    if (session?.accessToken === token) await refreshAccessToken();
    else await accessToken();
    return request(path, schema, init, true);
  }
  if (!response.ok) {
    const code = apiFailureCode(body);
    throw new ApiError(apiFailureMessage(response.status, code), response.status, code);
  }
  return parseContract(schema, body);
}
