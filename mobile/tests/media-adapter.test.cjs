const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { assetId } = require('./helpers/wire-fixtures.cjs');
const path = `/v1/assets/${assetId}/content`;
function harness(statuses = []) {
  const calls = [];
  const removed = [];
  let refreshed = 0;
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
  const api = createLoader({
    './client': {
      getAccessToken: async () => refreshed ? 'renewed' : 'initial',
      refreshAccessToken: async () => { refreshed++; },
      getApiUrl: (path) => `https://api.example.test${path}`, ApiError,
    },
    'expo-file-system/legacy': {
      cacheDirectory: 'file:///cache/',
      downloadAsync: async (url, uri, options) => { calls.push({ url, options }); const reply = statuses.shift(); return { uri, ...(typeof reply === 'number' ? { status: reply } : reply) };  },
      deleteAsync: async (uri) => removed.push(uri),
      getInfoAsync: async () => ({ exists: true, isDirectory: false, size: 2 }),
    },
  }, { fetch: async (url, options) => { calls.push({ url, options }); const status = statuses.shift(); return { status, ok: status >= 200 && status < 300, headers: new Headers({ 'Content-Type': 'application/octet-stream', 'Content-Length': '2' }), arrayBuffer: async () => new ArrayBuffer(2) }; } })('src/api/media.ts');
  return { api, calls, removed, refreshed: () => refreshed };
}
test('provider URLs are rejected before credentials or network use', async () => {
  const h = harness();
  await assert.rejects(h.api.readMedia('https://provider.test/private', 'application/octet-stream'), /request details/);
  assert.equal(h.calls.length, 0);
});
test('media reads authenticate only to Trove API and retry an expired session once', async () => {
  const h = harness([401, 200]);
  const signal = new AbortController().signal;
  assert.equal((await h.api.readMedia(path, 'application/octet-stream', signal)).byteLength, 2);
  assert.equal(h.calls[0].url, `https://api.example.test${path}`);
  assert.equal(h.calls[0].options.headers.Authorization, 'Bearer initial');
  assert.equal(h.calls[1].options.headers.Authorization, 'Bearer renewed');
  assert.equal(h.calls[0].options.signal, signal);
  assert.equal(h.calls[0].options.redirect, 'error');
  assert.equal(h.refreshed(), 1);
});
test('failed native media downloads are removed rather than returned as successful files', async () => {
  const h = harness([403]);
  await assert.rejects(h.api.downloadMedia(path, 'synthetic.bin', 'application/octet-stream'));
  assert.equal(h.removed.length, 1);
});
test('device-local media does not acquire or send authorization', async () => {
  const h = harness();
  const source = await h.api.mediaSource('file:///synthetic/image.png');
  assert.equal(source.uri, 'file:///synthetic/image.png');
  assert.equal(source.headers, undefined);
  assert.equal(await h.api.downloadMedia(source.uri, 'unused', 'image/png'), source.uri);
  assert.equal(h.calls.length, 0);
});

test('native media download verifies MIME and exact byte count', async () => {
  const success = harness([{ status: 200, headers: { 'Content-Type': 'application/octet-stream', 'Content-Length': '2' } }]);
  assert.match(await success.api.downloadMedia(path, 'synthetic.bin', 'application/octet-stream'), /^file:/);
  const truncated = harness([{ status: 200, headers: { 'Content-Type': 'application/octet-stream', 'Content-Length': '3' } }]);
  await assert.rejects(truncated.api.downloadMedia(path, 'synthetic.bin', 'application/octet-stream'), /incomplete/);
  assert.equal(truncated.removed.length, 1);
});

test('buffered media rejects a partial HTTP response instead of treating it as a full workbook', async () => {
  const h = harness([206]);
  await assert.rejects(h.api.readMedia(path, 'application/octet-stream'), /invalid response/);
});
