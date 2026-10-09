export type ConfirmationLink =
  | { kind: 'token'; tokenHash: string }
  | { kind: 'confirmed' }
  | { kind: 'failed'; message: string };

export function parseConfirmationLink(url: string): ConfirmationLink {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
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

  const tokenHash = value('token_hash') ?? value('token');
  return tokenHash ? { kind: 'token', tokenHash } : { kind: 'confirmed' };
}
