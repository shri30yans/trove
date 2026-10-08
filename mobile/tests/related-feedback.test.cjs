const { test } = require('node:test');
const assert = require('node:assert/strict');
const { QueryClient } = require('@tanstack/react-query');
const { createLoader } = require('./helpers/typescript-loader.cjs');
function harness() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let options;
  const state = { isPending: false, variables: undefined, error: null, mutate() {} };
  const useRelatedFeedback = createLoader({
    '@tanstack/react-query': { useQueryClient: () => client, useMutation: (value) => { options = value; return state; } },
    '../../api/search': {},
  })('src/features/memories/use-related-feedback.ts').useRelatedFeedback;
  return { client, state, render: useRelatedFeedback, options: () => options };
}
test('confirmed negative feedback cancels a late related read before removing its cached result', async () => {
  const h = harness();
  const key = ['memory', 'one', 'related'];
  h.client.setQueryData(key, { memories: [{ id: 'two' }, { id: 'three' }] });
  let aborted = false;
  const pending = h.client.fetchQuery({ queryKey: key, queryFn: ({ signal }) => new Promise(() => { signal.addEventListener('abort', () => { aborted = true; }); }) }).catch(() => null);
  h.render('one');
  await h.options().onSuccess({ saved: true }, { memoryId: 'one', relatedId: 'two', isRelated: false });
  assert.equal(aborted, true);
  assert.deepEqual(Array.from(h.client.getQueryData(key).memories, (memory) => memory.id), ['three']);
  await pending;
  h.client.clear();
});
test('feedback errors remain visible for their memory and cannot leak into a different detail screen', () => {
  const h = harness();
  h.state.variables = { memoryId: 'one', relatedId: 'two', isRelated: false };
  h.state.error = new Error('Unavailable');
  assert.equal(h.render('one').error, 'Unavailable');
  assert.equal(h.render('other').error, null);
  h.client.clear();
});
