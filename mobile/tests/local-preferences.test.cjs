const { test } = require('node:test');
const assert = require('node:assert/strict');
const { DatabaseSync } = require('node:sqlite');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { id } = require('./helpers/wire-fixtures.cjs');
function harness(initial = {}) {
  const legacy = new Map(Object.entries(initial));
  const db = new DatabaseSync(':memory:');
  db.exec('CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
  let releaseRead;
  let delayed = false;
  const store = {
    getItemSync: (key) => db.prepare('SELECT value FROM kv WHERE key = ?').get(key)?.value ?? null,
    setItemSync: (key, value) => db.prepare('INSERT INTO kv VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value').run(key, value),
  };
  const api = createLoader({
    'expo-sqlite/kv-store': store,
    '@react-native-async-storage/async-storage': {
      getItem: async (key) => delayed ? new Promise((resolve) => { releaseRead = () => resolve(legacy.get(key) ?? null); }) : legacy.get(key) ?? null,
      removeItem: async (key) => legacy.delete(key),
    },
    '../utils/sync-log': { logSync: () => {} },
  })('src/storage/local-preferences.ts');
  return { api, legacy, store, db, delay: () => { delayed = true; }, release: () => releaseRead() };
}
test('legacy preferences migrate to validated SQLite values', async () => {
  const h = harness({ 'trove.setting.background-sync.v1': 'false', 'trove.default-capture-space.v1': id, 'trove.search.history.v1': '["Synthetic"]' });
  try {
    assert.equal(await h.api.automaticSyncPreference.read(), false);
    assert.equal(await h.api.defaultSpacePreference.read(), id);
    assert.deepEqual(await h.api.searchHistoryPreference.read(), ['Synthetic']);
    assert.equal(h.legacy.size, 0);
  } finally { h.db.close(); }
});
test('a choice committed during migration wins over a late legacy read', async () => {
  const h = harness({ 'trove.search.history.v1': '["Synthetic"]' });
  try {
    h.delay();
    const pending = h.api.searchHistoryPreference.read();
    h.api.searchHistoryPreference.write(['Kept']);
    h.release();
    assert.deepEqual(await pending, ['Kept']);
  } finally { h.db.close(); }
});
test('clearing a destination cannot resurrect a stale legacy selection', async () => {
  const h = harness({ 'trove.default-capture-space.v1': id });
  try { h.api.defaultSpacePreference.write(null); assert.equal(await h.api.defaultSpacePreference.read(), null); }
  finally { h.db.close(); }
});
test('corrupt history stays intact and is surfaced instead of being replaced', async () => {
  const h = harness({ 'trove.search.history.v1': '[42]' });
  try {
    await assert.rejects(h.api.searchHistoryPreference.read(), /invalid/);
    assert.equal(h.legacy.get('trove.search.history.v1'), '[42]');
    assert.equal(h.store.getItemSync('trove.search.history.v1'), null);
  } finally { h.db.close(); }
});
test('unknown theme identifiers and malformed sync flags fail validation', async () => {
  const h = harness({ 'trove.setting.background-sync.v1': 'maybe' });
  try {
    h.store.setItemSync('trove.theme.v1', '"__proto__"');
    await assert.rejects(h.api.themePreference.read(), /invalid/);
    await assert.rejects(h.api.automaticSyncPreference.read(), /invalid/);
    assert.throws(() => h.api.defaultSpacePreference.write('not-a-uuid'), /invalid/);
  } finally { h.db.close(); }
});
test('an unset theme follows the phone while an explicit choice stays pinned', async () => {
  const fresh = harness();
  try { assert.equal(await fresh.api.themePreference.read(), null); } finally { fresh.db.close(); }
  const chosen = harness();
  try {
    chosen.store.setItemSync('trove.theme.v1', JSON.stringify('slate'));
    assert.equal(await chosen.api.themePreference.read(), 'slate');
  } finally { chosen.db.close(); }
  const explicitLight = harness();
  try {
    await explicitLight.api.themePreference.read();
    explicitLight.api.themePreference.write('light');
    assert.equal(await explicitLight.api.themePreference.read(), 'light');
  } finally { explicitLight.db.close(); }
});

test('consecutive history updates derive from the durable value and cannot lose a submission', async () => {
  const h = harness();
  try {
    await h.api.searchHistoryPreference.read();
    const first = h.api.searchHistoryPreference.update((current) => ['First', ...current]);
    const second = h.api.searchHistoryPreference.update((current) => ['Second', ...current]);
    assert.deepEqual(first, ['First']);
    assert.deepEqual(second, ['Second', 'First']);
    assert.deepEqual(await h.api.searchHistoryPreference.read(), ['Second', 'First']);
  } finally { h.db.close(); }
});
test('history update cannot overwrite unmigrated legacy data', () => {
  const h = harness({ 'trove.search.history.v1': '["Legacy"]' });
  try {
    assert.throws(() => h.api.searchHistoryPreference.update(() => ['New']), /still loading/);
    assert.equal(h.store.getItemSync('trove.search.history.v1'), null);
    assert.equal(h.legacy.get('trove.search.history.v1'), '["Legacy"]');
  } finally { h.db.close(); }
});
