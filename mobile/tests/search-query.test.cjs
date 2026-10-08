const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const query = require('@tanstack/react-query');
function load(file, mocks) {
  const mod = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText,
    { module: mod, exports: mod.exports, require: (name) => mocks[name] ?? require(name) });
  return mod.exports;
}
test('search uses the intended endpoint and forwards query cancellation', async () => {
  const calls = [];
  const { memorySearchOptions } = load('src/features/search/search-query.ts', {
    '../../api/memories': { getMemories: async (filters, signal) => { calls.push({ filters, signal }); return { memories: [] }; } },
    '../../api/search': { searchMemories: async (filters, signal) => { calls.push({ filters, signal }); return { memories: [], semanticSearch: true }; } },
  });
  const client = new query.QueryClient();
  try {
    const result = await client.fetchQuery(memorySearchOptions({ query: 'hello', spaceId: 'one' }));
    assert.equal(result.semanticSearch, true);
    assert.ok(calls[0].signal instanceof AbortSignal);
    await client.fetchQuery(memorySearchOptions({ query: '', kind: 'image' }));
    assert.equal(calls[1].filters.limit, 50);
    assert.equal(calls[1].filters.kind, 'image');
  } finally { client.clear(); }
});
test('distinct filters isolate late responses and invalidation refreshes cached results', async () => {
  let resolveOld;
  let attempts = 0;
  const { memorySearchOptions, memorySearchKey } = load('src/features/search/search-query.ts', {
    '../../api/memories': {},
    '../../api/search': { searchMemories: async (filters) => {
      attempts++;
      if (filters.spaceId === 'old') return new Promise((resolve) => { resolveOld = resolve; });
      return { memories: [filters.spaceId], semanticSearch: false };
    } },
  });
  const client = new query.QueryClient();
  try {
    const old = client.fetchQuery(memorySearchOptions({ query: 'hello', spaceId: 'old' }));
    const current = memorySearchOptions({ query: 'hello', spaceId: 'new' });
    await client.fetchQuery(current);
    resolveOld({ memories: ['old'], semanticSearch: false });
    await old;
    assert.equal(client.getQueryData(current.queryKey).memories[0], 'new');
    await client.invalidateQueries({ queryKey: memorySearchKey });
    assert.equal(client.getQueryState(current.queryKey).isInvalidated, true);
    await client.fetchQuery(current);
    assert.equal(attempts, 3);
  } finally { client.clear(); }
});
test('read failure surfaces once without automatic retries', async () => {
  const { createQueryClient } = load('src/providers/query-provider.tsx', {});
  const client = createQueryClient();
  let attempts = 0;
  try {
    await assert.rejects(client.fetchQuery({ queryKey: ['failure'], queryFn: () => { attempts++; throw new Error('Unavailable'); } }), /Unavailable/);
    assert.equal(attempts, 1);
  } finally { client.clear(); }
});
