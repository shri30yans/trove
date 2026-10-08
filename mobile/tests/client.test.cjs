const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { z } = require('zod');
const responseSchema = z.object({ value: z.string() });
function harness(fetch) {
  const values = new Map([['trove.auth-session.v1', JSON.stringify({
    accessToken: 'test-token',
    refreshToken: 'test-refresh-token',
    expiresAt: Date.now() + 60 * 60 * 1000,
  })]]);
  const store = {
    getItemAsync: async (key) => values.get(key) ?? null,
    deleteItemAsync: async (key) => { values.delete(key); },
    setItemAsync: async (key, value) => { values.set(key, value); },
  };
  const load = createLoader({ 'expo-secure-store': store }, {
    process: { env: { EXPO_PUBLIC_API_URL: 'https://api.test' } }, __DEV__: true, fetch,
  });
  const api = load('src/api/client.ts');
  return { api, values };
}
test('API requests have no artificial deadline and preserve caller cancellation', async () => {
  let started;
  const ready = new Promise((resolve) => { started = resolve; });
  const controller = new AbortController();
  const h = harness(async (_, { signal }) => {
    started(signal);
    return new Promise((_, reject) => signal.addEventListener('abort', () => reject(Error('aborted'))));
  });
  const result = h.api.request('/v1/memories', responseSchema, { signal: controller.signal });
  const requestSignal = await ready;
  assert.equal(requestSignal, controller.signal);
  controller.abort();
  await assert.rejects(result, /Request cancelled/);
});
test('invalid success JSON is not treated as acknowledgement', async () => {
  const h = harness(async () => ({ status: 200, ok: true, json: async () => { throw Error('invalid json'); } }));
  await assert.rejects(h.api.request('/v1/memories', responseSchema), /unreadable response/);
});
test('non-JSON API errors retain their HTTP status for retry classification', async () => {
  const h = harness(async () => ({ status: 413, ok: false, json: async () => { throw Error('not json'); } }));
  await assert.rejects(h.api.request('/v1/memories', responseSchema), (error) => error instanceof h.api.ApiError && error.status === 413);
});

test('storage quota errors explain that the local save is kept', async () => {
  const load = createLoader();
  const { apiFailureMessage } = load('src/api/messages.ts');
  assert.match(apiFailureMessage(413, 'storage_quota_exceeded'), /kept on your device/i);
});

test('provider details never appear in API failure copy; status and code remain available', async () => {
  const h = harness(async () => ({ status: 503, ok: false, json: async () => ({ error: { code: 'storage_unavailable', message: 'Raw provider failure: secret diagnostic' } }) }));
  await assert.rejects(h.api.request('/v1/memories', responseSchema), (error) => {
    assert.equal(error.status, 503);
    assert.equal(error.code, 'storage_unavailable');
    assert.doesNotMatch(error.message, /secret|storage_unavailable|provider/);
    assert.match(error.message, /try again/i);
    return true;
  });
});

test('valid JSON with missing contract fields fails at the transport boundary', async () => {
  const h = harness(async () => ({ status: 200, ok: true, json: async () => ({ wrong: 'field' }) }));
  await assert.rejects(h.api.request('/v1/memories', responseSchema), /invalid response/);
});
test('a schema determines the actual returned type and strips unknown response extensions', async () => {
  const h = harness(async () => ({ status: 200, ok: true, json: async () => ({ value: 'valid', extension: 42 }) }));
  const result = await h.api.request('/v1/memories', responseSchema);
  assert.deepEqual(result, { value: 'valid' });
});

test('Supabase credentials go only to the Trove auth API and the rotated session is stored securely', async () => {
  let sent;
  const h = harness(async (url, init) => {
    sent = { url, init };
    return { status: 200, ok: true, json: async () => ({
      status: 'authenticated',
      session: { accessToken: 'supabase-access', refreshToken: 'supabase-refresh', tokenType: 'Bearer', expiresIn: 3600 },
    }) };
  });

  await h.api.signInWithPassword(' reader@example.test ', 'synthetic-password');

  assert.equal(sent.url, 'https://api.test/v1/auth/sign-in');
  assert.equal(sent.init.headers.Accept, 'application/json');
  assert.deepEqual(JSON.parse(sent.init.body), { email: 'reader@example.test', password: 'synthetic-password' });
  const stored = JSON.parse(h.values.get('trove.auth-session.v1'));
  assert.equal(stored.accessToken, 'supabase-access');
  assert.equal(stored.refreshToken, 'supabase-refresh');
  assert.equal(h.values.has('trove.access-token.v1'), false);
});

test('an old local-only session is cleared and cannot sign in automatically', async () => {
  const h = harness(async () => { throw new Error('no request should be made'); });
  h.values.set('trove.auth-session.v1', JSON.stringify({ accessToken: 'legacy-local-token', refreshToken: null, expiresAt: Date.now() + 60_000 }));

  assert.equal(await h.api.hasSavedSession(), false);
  assert.equal(h.values.has('trove.auth-session.v1'), false);
  assert.equal(h.values.has('trove.access-token.v1'), false);
});
