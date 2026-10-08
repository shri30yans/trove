const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { detail, assetId, completedAssetId, date } = require('./helpers/wire-fixtures.cjs');
function harness(response = { memory: detail }, completion = { assetId, status: 'uploaded', byteSize: 10 }) {
  const calls = [];
  let uploadCalls = 0;

  const mocks = {
    'expo-file-system/legacy': {
      getInfoAsync: async () => ({ exists: true, size: 10 }),
      FileSystemUploadType: { BINARY_CONTENT: 0 },
      FileSystemSessionType: { FOREGROUND: 1 },
      createUploadTask: () => ({ uploadAsync: async () => { uploadCalls++; return { status: 200, body: JSON.stringify({ assetId, byteSize: 10 }) }; }, cancelAsync: async () => {} }),
    },
    '../utils/sync-log': { logSync: () => {} },
    './client': { ApiError: class extends Error { constructor(message, status) { super(message); this.status = status; } }, getAccessToken: async () => 'token', getApiUrl: (path) => `https://api.test${path}`, request: async (path, schema, init) => {
      calls.push({ path, init });
      const result = path === '/v1/uploads' ? { assetId, uploadPath: `/v1/uploads/${assetId}/content`, method: 'PUT', headers: {} } : path === '/v1/memories' ? response : completion;
      const parsed = schema.safeParse(result);
      if (!parsed.success) throw Error('Trove returned an invalid response.');
      return parsed.data;
    } },
  };
  const api = createLoader(mocks)('src/api/captures.ts');
  return { api, calls, uploadCalls: () => uploadCalls };
}
const attachment = { asset: { uri: 'file:///docs/a.txt', filename: 'a.txt', mimeType: 'text/plain' } };
test('resume skips completed files and checkpoints new files before creating the memory', async () => {
  const h = harness();
  const checkpoints = [];
  await h.api.submitCapture({ kind: 'file', capturedAt: date, attachments: [attachment, attachment] }, { key: 'stable', assetIds: [completedAssetId], onUploaded: async (ids) => {
    assert.ok(!h.calls.some((call) => call.path === '/v1/memories'));
    checkpoints.push([...ids]);
  } });
  assert.equal(h.uploadCalls(), 1);
  assert.deepEqual(checkpoints, [[completedAssetId, assetId]]);
  const created = h.calls.find((call) => call.path === '/v1/memories');
  assert.equal(created.init.headers['Idempotency-Key'], 'stable');
  assert.deepEqual(JSON.parse(created.init.body).assetIds, [completedAssetId, assetId]);
});
test('malformed server acknowledgement cannot remove a local save', async () => {
  const h = harness({ memory: null });
  await assert.rejects(h.api.submitCapture({ kind: 'text', capturedAt: date }, { key: 'stable', assetIds: [], onUploaded: async () => {} }), /invalid response/);
});
test('failed checkpoint prevents memory creation', async () => {
  const h = harness();
  await assert.rejects(h.api.submitCapture({ kind: 'file', capturedAt: date, attachments: [attachment] }, { key: 'stable', assetIds: [], onUploaded: async () => { throw Error('disk full'); } }), /disk full/);
  assert.ok(!h.calls.some((call) => call.path === '/v1/memories'));
});

for (const completion of [{ assetId, status: 'uploaded' }, { assetId, status: 'attached', byteSize: 9 }]) {
  test(`invalid completion size ${completion.byteSize} cannot checkpoint or create a memory`, async () => {
    const h = harness({ memory: detail }, completion);
    let checkpointed = false;
    await assert.rejects(h.api.submitCapture({ kind: 'file', capturedAt: date, attachments: [attachment] }, {
      key: 'stable', assetIds: [], onUploaded: async () => { checkpointed = true; },
    }), /invalid response/);
    assert.equal(checkpointed, false);
    assert.ok(!h.calls.some((call) => call.path === '/v1/memories'));
  });
}
