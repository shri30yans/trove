const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
function harness(replies, cleanupError = null) {
  const removed = [];
  const requests = [];
  let refreshes = 0;
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
  const { downloadApiFile } = createLoader({
    './client': { ApiError, getApiUrl: (path) => `https://api.example.test${path}`, getAccessToken: async () => 'initial', refreshAccessToken: async () => { refreshes++; return 'renewed'; } },
    'expo-file-system/legacy': {
      downloadAsync: async (url, uri, options) => { requests.push({ url, options }); const next = replies.shift(); if (next instanceof Error) throw next; return { uri, ...next }; },
      deleteAsync: async (uri) => { removed.push(uri); if (cleanupError) throw cleanupError; },
      getInfoAsync: async () => ({ exists: true, isDirectory: false, size: 2 }),
      readAsStringAsync: async () => '{}',
    },
  }, { console: { warn() {} } })('src/api/download.ts');
  return { download: () => downloadApiFile('/v1/export/markdown', 'file:///cache/synthetic.zip', 'application/zip'), removed, requests, refreshes: () => refreshes };
}
test('interrupted native download cleans its partial destination and retains the transport cause', async () => {
  const failure = new Error('synthetic transport failure');
  const h = harness([failure]);
  await assert.rejects(h.download(), (error) => error.message === 'Could not connect to Trove.' && error.cause === failure);
  assert.deepEqual(h.removed, ['file:///cache/synthetic.zip']);
});
test('expired download authentication retries once and never returns either error file', async () => {
  const h = harness([{ status: 401 }, { status: 401 }]);
  await assert.rejects(h.download(), (error) => error.status === 401);
  assert.equal(h.requests.length, 2);
  assert.equal(h.refreshes(), 1);
  assert.equal(h.removed.length, 2);
});
test('cleanup failure cannot replace the invalid-file error', async () => {
  const h = harness([{ status: 200, headers: { 'content-type': 'application/zip', 'content-length': '3' } }], new Error('synthetic cleanup failure'));
  await assert.rejects(h.download(), /incomplete or invalid file/);
  assert.equal(h.removed.length, 1);
});
