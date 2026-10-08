const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const input = { memoryIds: ['one', 'two'], fromSpaceId: 'source', toSpaceId: 'target' };
test('confirmed moves reconcile while another item is still pending and retain failures for retry', async () => {
  let release;
  const confirmed = [];
  const api = createLoader({ '../../api/memories': { moveMemory: async (id) => id === 'one' ? { memory: { id } } : new Promise((_, reject) => { release = reject; }) } })('src/features/spaces/move-memory-batch.ts');
  const pending = api.moveMemoryBatch(input, (memory) => confirmed.push(memory.id));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(confirmed, ['one']);
  release(new Error('Unavailable'));
  const result = await pending;
  assert.deepEqual(Array.from(result.confirmedIds), ['one']);
  assert.deepEqual(Array.from(result.failedIds), ['two']);
});
test('presentation reconciliation failure cannot turn a server-confirmed move into a retry', async () => {
  const events = [];
  const api = createLoader({ '../../api/memories': { moveMemory: async (id) => ({ memory: { id } }) } }, { console: { error: (...event) => events.push(event) } })('src/features/spaces/move-memory-batch.ts');
  const result = await api.moveMemoryBatch({ ...input, memoryIds: ['one', 'one'] }, () => { throw new Error('Observer failure'); });
  assert.deepEqual(Array.from(result.confirmedIds), ['one']);
  assert.equal(result.failedIds.length, 0);
  assert.equal(result.refreshRequired, true);
  assert.equal(events.length, 1);
});
