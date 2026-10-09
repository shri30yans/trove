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

test('a provider callback without a token is accepted only when it has no provider error', () => {
  assert.deepEqual(parseConfirmationLink('trove://confirm-email#type=signup'), { kind: 'confirmed' });
  assert.deepEqual(parseConfirmationLink('trove://confirm-email?error=access_denied'), {
    kind: 'failed',
    message: 'This confirmation link is invalid. Request a new one below.',
  });
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
