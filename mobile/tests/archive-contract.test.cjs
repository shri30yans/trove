const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const load = createLoader();
const { validateArchivePrefix } = load('src/api/schemas/exports.ts');
const { validateBinaryDownload } = load('src/api/schemas/binary.ts');
function validateArchiveDownload(response, file, prefix) {
  validateBinaryDownload(response, file, 'application/zip');
  validateArchivePrefix(prefix);
}
const response = { status: 200, headers: { 'Content-Type': 'application/zip', 'Content-Length': '128' } };
const file = { exists: true, isDirectory: false, size: 128 };
test('complete ZIP download accepts case-insensitive HTTP header names', () => {
  assert.doesNotThrow(() => validateArchiveDownload(response, file, 'UEsDBA=='));
});
test('archive rejects partial, malformed, truncated and missing downloads', () => {
  for (const [reply, info, signature] of [
    [{ ...response, status: 206 }, file, 'UEsDBA=='],
    [{ ...response, headers: { 'Content-Type': 'text/html', 'Content-Length': '128' } }, file, 'UEsDBA=='],
    [response, { ...file, size: 127 }, 'UEsDBA=='],
    [response, { exists: false }, 'UEsDBA=='],
    [response, file, 'PGh0bQ=='],
    [{ ...response, headers: { 'Content-Type': 'application/zip' } }, file, 'UEsDBA=='],
  ]) assert.throws(() => validateArchiveDownload(reply, info, signature));
});
function downloadHarness(replies) {
  const removed = [];
  const requests = [];
  let refreshes = 0;
  const adapter = createLoader({
    'expo-file-system/legacy': {
      cacheDirectory: 'file:///cache/',
      EncodingType: { Base64: 'base64' },
      downloadAsync: async (url, path, options) => {
        requests.push({ url, options });
        return { uri: path, ...replies.shift() };
      },
      getInfoAsync: async () => file,
      readAsStringAsync: async (_, options) => options ? 'UEsDBA==' : '{}',
      deleteAsync: async (uri) => removed.push(uri),
    },
    './client': {
      getApiUrl: (path) => `https://api.example.test${path}`,
      getAccessToken: async () => 'initial-token',
      refreshAccessToken: async () => { refreshes += 1; return 'renewed-token'; },
    },
  })('src/api/export.ts');
  return { adapter, removed, requests, refreshes: () => refreshes };
}
test('expired export session removes the failed file and retries with renewed authorization', async () => {
  const h = downloadHarness([{ status: 401 }, response]);
  assert.match(await h.adapter.downloadMarkdownArchive(), /^file:\/\/\/cache\/.*\.zip$/);
  assert.equal(h.removed.length, 1);
  assert.equal(h.refreshes(), 1);
  assert.equal(h.requests[1].options.headers.Authorization, 'Bearer renewed-token');
});
test('malformed successful export removes the downloaded file', async () => {
  const h = downloadHarness([{ status: 200, headers: { 'Content-Type': 'text/html', 'Content-Length': '128' } }]);
  await assert.rejects(h.adapter.downloadMarkdownArchive(), /invalid file/);
  assert.equal(h.removed.length, 1);
});
test('invalid Space identifier is rejected before downloading', async () => {
  const h = downloadHarness([]);
  await assert.rejects(h.adapter.downloadMarkdownArchive('invalid'), /request details/);
  assert.equal(h.requests.length, 0);
});
