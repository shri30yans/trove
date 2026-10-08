const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { card, detail, id, assetId, date } = require('./helpers/wire-fixtures.cjs');
const load = createLoader();
const memories = load('src/api/schemas/memories.ts');
const spaces = load('src/api/schemas/spaces.ts');
const search = load('src/api/schemas/search.ts');
const preferences = load('src/api/schemas/preferences.ts');
const overview = load('src/api/schemas/overview.ts');
const uploads = load('src/api/schemas/uploads.ts');
const auth = load('src/api/schemas/auth.ts');
const plans = load('src/api/schemas/plans.ts');
const cases = [
  ['memory list', memories.memoryListResponseSchema, { memories: [{ ...card, description: null, userNote: null, pageText: null, createdAt: date, previewUrl: null }], nextCursor: null }],
  ['memory detail', memories.memoryResponseSchema, { memory: detail }],
  ['spaces', spaces.spacesResponseSchema, { spaces: [{ id, name: 'Synthetic', description: null, color: null, icon: null, createdAt: date, updatedAt: date, memoryCount: 0 }] }],
  ['created space', spaces.spaceResponseSchema, { space: { id, name: 'Synthetic', description: null, color: null, icon: null, createdAt: date, updatedAt: date } }],
  ['preferences', preferences.preferencesResponseSchema, { preferences: { resurfacingEnabled: false, resurfacingCadence: 'weekly', embeddingsEnabled: false, embeddingsAvailable: false } }],
  ['search', search.searchResponseSchema, { query: 'Synthetic', semanticSearch: true, memories: [{ ...card, description: null, userNote: null, pageText: null, score: 0.8, matchType: 'meaning', matchExcerpt: 'Synthetic', previewUrl: null }] }],
  ['related', search.relatedResponseSchema, { memories: [{ ...card, similarity: 0.8, relation: 'same_topic', reason: 'Shared topic', previewUrl: null }] }],
  ['feedback', search.feedbackResponseSchema, { saved: true }],
  ['explore', overview.exploreSchema, { months: [{ month: '2026-10-01', memoryCount: 2 }] }],
  ['updates', overview.updatesResponseSchema, { enabled: true, cadence: 'weekly', updates: [{ memory: (({status, ...summary}) => ({ ...summary, previewUrl: null }))(card), relatedTo: { id, title: null, capturedAt: date }, reason: 'Synthetic relation', similarity: 0.8 }] }],
  ['upload allocation', uploads.uploadResponseSchema, { assetId, uploadPath: `/v1/uploads/${assetId}/content`, method: 'PUT', headers: { 'Content-Type': 'text/plain' } }],
  ['upload completion', uploads.uploadCompleteSchema, { assetId, status: 'uploaded', byteSize: 10 }],
  ['account deletion request', auth.accountDeletionRequestSchema, { requestedAt: date, deleteAfter: '2026-10-15T00:00:00.000Z', deletionCancellable: true }],
  ['account deletion status', auth.accountDeletionStatusSchema, { deletionScheduled: true, deleteAfter: '2026-10-15T00:00:00.000Z', deletionComplete: false, deletionCancellable: true }],
  ['plan', plans.planResponseSchema, { plan: { id: 'free', name: 'Free', storageLimitBytes: 200000000, storageUsedBytes: 1000000, storageRemainingBytes: 199000000 } }],
];
for (const [name, schema, value] of cases) {
  test(`${name} validates its documented wire projection`, () => assert.equal(schema.safeParse(value).success, true));
  test(`${name} rejects a missing top-level contract field`, () => {
    const invalid = { ...value }; delete invalid[Object.keys(invalid)[0]];
    assert.equal(schema.safeParse(invalid).success, false);
  });
}
test('a partial card cannot acknowledge a capture or masquerade as a full detail response', () => {
  assert.equal(memories.memoryResponseSchema.safeParse({ memory: card }).success, false);
  assert.equal(memories.memoryResponseSchema.safeParse({ memory: { ...detail, status: 'unknown' } }).success, false);
});
test('preferences updates cannot write server capability flags', () => {
  assert.equal(preferences.preferencePatchSchema.safeParse({ embeddingsAvailable: true }).success, false);
  assert.equal(preferences.preferencePatchSchema.safeParse({}).success, false);
});
test('request validation rejects invalid ownership identifiers', () => {
  assert.equal(memories.memoryPatchSchema.safeParse({ spaceIds: ['not-an-id'] }).success, false);
});

test('remote media contracts accept only resource-scoped Trove API paths', () => {
  const media = load('src/api/schemas/media.ts');
  assert.equal(media.mediaPathSchema.safeParse(`/v1/assets/${assetId}/content`).success, true);
  assert.equal(media.mediaPathSchema.safeParse(`/v1/memories/${id}/preview`).success, true);
  for (const path of ['https://storage.example.test/private?signature=secret', '//external.test/file', '/v1/assets/../content', `/v1/assets/${assetId}/content?token=secret`]) {
    assert.equal(media.mediaPathSchema.safeParse(path).success, false);
  }
  const asset = { id: assetId, filename: null, mimeType: 'image/png', byteSize: 1, status: 'attached', role: 'original', createdAt: date, url: `/v1/assets/${assetId}/content` };
  assert.equal(memories.memoryResponseSchema.safeParse({ memory: { ...detail, assets: [asset] } }).success, true);
  assert.equal(memories.memoryResponseSchema.safeParse({ memory: { ...detail, assets: [{ ...asset, url: `/v1/assets/${id}/content` }] } }).success, false);
});

test('move requests require two distinct owned-resource identifiers', () => {
  assert.equal(memories.moveMemoryRequestSchema.safeParse({ fromSpaceId: id, toSpaceId: assetId }).success, true);
  assert.equal(memories.moveMemoryRequestSchema.safeParse({ fromSpaceId: id, toSpaceId: id }).success, false);
  assert.equal(memories.moveMemoryRequestSchema.safeParse({ fromSpaceId: id }).success, false);
  assert.equal(memories.moveMemoryRequestSchema.safeParse({ fromSpaceId: id, toSpaceId: assetId, userId: id }).success, false);
});
