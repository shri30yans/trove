const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
function harness() {
  let selection = null;
  const replies = new Map();
  const queries = [];
  const hook = createLoader({
    react: { useState: () => [selection, (next) => { selection = typeof next === 'function' ? next(selection) : next; }], useCallback: (fn) => fn },
    'react-native': { Alert: { alert() {} } },
    'expo-router': { useRouter: () => ({ push() {}, replace() {}, back() {} }), useSegments: () => [] },
    '@tanstack/react-query': {
      useQueryClient: () => ({ cancelQueries: async () => {}, setQueryData() {}, removeQueries() {} }),
      useQuery: (options) => {
        queries.push(options);
        return replies.get(JSON.stringify(options.queryKey)) ?? { isPending: true, isError: false };
      },
    },
    '../../api/memories': {}, '../../api/search': {},
    './use-related-feedback': { useRelatedFeedback: () => ({ error: null, pendingId: null, submit() {} }) },
  })('src/features/memories/use-memory-details.ts').useMemoryDetails;
  const options = { memories: [], pendingMemories: [], upsertMemory() {}, removeMemory() {}, loadWorkspace: async () => {}, showToast() {} };
  return { replies, queries, options, render: () => hook(options) };
}
test('changing detail selection does not render a prior memory response', async () => {
  const h = harness();
  h.replies.set(JSON.stringify(['memory', 'one']), { data: { memory: { id: 'one' } }, isPending: false });
  await h.render().loadMemoryDetails('one');
  assert.equal(h.render().detailMemory.id, 'one');
  await h.render().loadMemoryDetails('two');
  assert.equal(h.render().detailMemory, null);
  assert.equal(h.render().detailLoading, true);
});
test('a tapped list preview renders immediately while full detail loads', async () => {
  const h = harness();
  const preview = { id: 'one', title: 'List card', summary: 'Cached preview' };
  h.options.memories = [preview];
  await h.render().openMemory(preview);
  const result = h.render();
  assert.equal(result.detailMemory, preview);
  assert.equal(result.detailLoading, false);
  assert.equal(h.queries.slice(-2).every((query) => query.enabled), true);
});
test('failed detail cannot expose a partial list card as editable details', async () => {
  const h = harness();
  h.options.memories = [{ id: 'one', title: 'List card' }];
  h.replies.set(JSON.stringify(['memory', 'one']), { error: new Error('Unavailable'), isError: true, isPending: false });
  await h.render().loadMemoryDetails('one');
  const result = h.render();
  assert.equal(result.detailMemory, null);
  assert.equal(result.detailError, 'Unavailable');
});
test('pending details stay local and disable remote detail and related reads', async () => {
  const h = harness();
  const pending = { id: 'local-one', localPending: true };
  h.options.pendingMemories = [pending];
  await h.render().openMemory(pending);
  const result = h.render();
  assert.equal(result.detailMemory, pending);
  assert.equal(result.detailLoading, false);
  assert.equal(h.queries.slice(-2).every((query) => query.enabled === false), true);
});
