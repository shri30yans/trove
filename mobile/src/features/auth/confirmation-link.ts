export type ConfirmationLink =
  | { kind: 'token'; tokenHash: string }
  | { kind: 'session'; accessToken: string; refreshToken: string; expiresIn: number }
  | { kind: 'confirmed' }
  | { kind: 'failed'; message: string };

export function parseConfirmationLink(url: string): ConfirmationLink {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return { kind: 'failed', message: 'This confirmation link is invalid. Request a new one below.' };
  }

  if (parsed.protocol !== 'trove:' || parsed.hostname !== 'confirm-email') {
    return { kind: 'failed', message: 'This confirmation link is invalid. Request a new one below.' };
  }

  const fragment = new URLSearchParams(parsed.hash.replace(/^#/, ''));
  const value = (key: string) => parsed.searchParams.get(key) ?? fragment.get(key);
  const errorCode = value('error_code') ?? value('error');
  const errorDescription = value('error_description') ?? value('message') ?? '';
  if (errorCode || errorDescription) {
    const details = `${errorCode ?? ''} ${errorDescription}`.toLowerCase();
    return {
      kind: 'failed',
      message: details.includes('expir')
        ? 'This confirmation link has expired. Request a new one below.'
        : 'This confirmation link is invalid. Request a new one below.',
    };
  }

  const type = value('type');
  if (type && type !== 'signup') {
    return { kind: 'failed', message: 'This confirmation link is invalid. Request a new one below.' };
  }

  const accessToken = value('access_token');
  const refreshToken = value('refresh_token');
  if (accessToken || refreshToken) {
    const expiresIn = Number(value('expires_in'));
    const tokenType = value('token_type')?.toLowerCase();
    if (type !== 'signup' || !accessToken || !refreshToken || tokenType !== 'bearer' || !Number.isInteger(expiresIn) || expiresIn <= 0) {
      return { kind: 'failed', message: 'This confirmation link is invalid. Request a new one below.' };
    }
    return { kind: 'session', accessToken, refreshToken, expiresIn };
  }

  const tokenHash = value('token_hash') ?? value('token');
  if (tokenHash) return { kind: 'token', tokenHash };
  return type === 'signup'
    ? { kind: 'confirmed' }
    : { kind: 'failed', message: 'This confirmation link is invalid. Request a new one below.' };
}
