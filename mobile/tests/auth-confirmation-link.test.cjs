const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');

const { parseConfirmationLink: parseFromModule } = createLoader()('src/features/auth/confirmation-link.ts');
const parseConfirmationLink = (url) => Object.assign({}, parseFromModule(url));

test('confirmation callback verifies a token hash before showing success', () => {
  assert.deepEqual(parseConfirmationLink('trove://confirm-email?token_hash=synthetic-token'), {
    kind: 'token',
    tokenHash: 'synthetic-token',
  });
});

test('confirmation callback accepts a complete Supabase signup session', () => {
  assert.deepEqual(parseConfirmationLink('trove://confirm-email#access_token=access&refresh_token=refresh&expires_in=3600&token_type=bearer&type=signup'), {
    kind: 'session',
    accessToken: 'access',
    refreshToken: 'refresh',
    expiresIn: 3600,
  });
});

test('a provider callback without a session is accepted only when it has no provider error', () => {
  assert.deepEqual(parseConfirmationLink('trove://confirm-email#type=signup'), { kind: 'confirmed' });
  assert.equal(parseConfirmationLink('trove://confirm-email').kind, 'failed');
  assert.deepEqual(parseConfirmationLink('trove://confirm-email?error=access_denied'), {
    kind: 'failed',
    message: 'This confirmation link is invalid. Request a new one below.',
  });
});

test('wrong schemes and incomplete callback sessions fail visibly', () => {
  assert.equal(parseConfirmationLink('https://example.test/confirm-email#type=signup').kind, 'failed');
  assert.equal(parseConfirmationLink('trove://confirm-email#access_token=access&type=signup').kind, 'failed');
  assert.equal(parseConfirmationLink('trove://confirm-email#access_token=access&refresh_token=refresh&expires_in=0&token_type=bearer&type=signup').kind, 'failed');
  assert.equal(parseConfirmationLink('trove://confirm-email#access_token=access&refresh_token=refresh&expires_in=3600&token_type=bearer&type=recovery').kind, 'failed');
});

test('expired confirmation errors in the query or fragment offer a fresh link', () => {
  for (const url of [
    'trove://confirm-email?error_code=otp_expired',
    'trove://confirm-email#error=access_denied&error_description=The+email+link+has+expired',
  ]) {
    assert.deepEqual(parseConfirmationLink(url), {
      kind: 'failed',
      message: 'This confirmation link has expired. Request a new one below.',
    });
  }
});

test('malformed confirmation links fail visibly instead of becoming success', () => {
  assert.deepEqual(parseConfirmationLink('not a URL'), {
    kind: 'failed',
    message: 'This confirmation link is invalid. Request a new one below.',
  });
});
