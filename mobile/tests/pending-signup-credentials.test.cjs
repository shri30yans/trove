const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');

const credentials = createLoader()('src/features/auth/pending-signup-credentials.ts');

test('stashed signup credentials are honored only for the registered address', () => {
  credentials.clearPendingSignupCredentials();
  credentials.stashPendingSignupCredentials('User@Example.test', 'synthetic-password');
  assert.equal(credentials.peekPendingSignupCredentials('user@example.test'), 'synthetic-password');
  assert.equal(credentials.peekPendingSignupCredentials('other@example.test'), null);
  credentials.clearPendingSignupCredentials();
  assert.equal(credentials.peekPendingSignupCredentials('user@example.test'), null);
});

test('a newer sign-up replaces the pending credentials', () => {
  credentials.clearPendingSignupCredentials();
  credentials.stashPendingSignupCredentials('user@example.test', 'first-password');
  credentials.stashPendingSignupCredentials('user@example.test', 'second-password');
  assert.equal(credentials.peekPendingSignupCredentials('user@example.test'), 'second-password');
  credentials.clearPendingSignupCredentials();
});
