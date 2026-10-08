const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { projectMemoryLibrary } = createLoader()('src/features/workspace/memory-library.ts');
const confirmed = [{ memory: { id: 'new', title: 'Edited', replacesLocalId: 'local-one' }, revision: 2 }];
const page = (memories, startedRevision = 0) => ({ memories, nextCursor: null, startedRevision });
test('late list cannot erase a newly acknowledged save', () => {
  const result = projectMemoryLibrary([page([{ id: 'old' }])], confirmed, new Set());
  assert.equal(result[0].id, 'new');
  assert.equal(result.length, 2);
});
test('late list cannot replace a newer confirmed edit', () => {
  const result = projectMemoryLibrary([page([{ id: 'new', title: 'Old' }], 1)], confirmed, new Set());
  assert.equal(result[0].title, 'Edited');
});
test('subsequent list can update processing state while preserving local route identity', () => {
  const result = projectMemoryLibrary([page([{ id: 'new', status: 'ready' }], 2)], confirmed, new Set());
  assert.equal(result[0].status, 'ready');
  assert.equal(result[0].replacesLocalId, 'local-one');
});
test('deleted memories stay absent across stale pages and confirmations', () => {
  assert.equal(projectMemoryLibrary([page([{ id: 'new' }])], confirmed, new Set(['new'])).length, 0);
});
test('overlapping pagination has one record per memory', () => {
  const result = projectMemoryLibrary([page([{ id: 'one' }]), page([{ id: 'one' }, { id: 'two' }])], [], new Set());
  assert.deepEqual(Array.from(result, (memory) => memory.id), ['one', 'two']);
});
