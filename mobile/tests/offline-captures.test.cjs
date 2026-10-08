const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

function harness(initial = '[]', existingDatabase) {
  let stored = initial;
  let connected = true;
  let submit = async () => ({ id: 'remote' });
  let failWrite = false;
  let failDelete = false;
  const deleted = [];
  const db = existingDatabase ?? new DatabaseSync(':memory:');
  class CaptureFileError extends Error {}
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
  const sqlite = {
    execSync: (sql) => db.exec(sql),
    runSync: (sql, ...args) => { if (failWrite) throw Error('disk full'); return db.prepare(sql).run(...args); },
    getFirstSync: (sql, ...args) => db.prepare(sql).get(...args) ?? null,
    getAllSync: (sql, ...args) => db.prepare(sql).all(...args),
    withTransactionSync: (fn) => {
      db.exec('BEGIN');
      try { fn(); db.exec('COMMIT'); } catch (error) { db.exec('ROLLBACK'); throw error; }
    },
    closeAsync: async () => {},
  };
  const mocks = {
    '@react-native-async-storage/async-storage': { getItem: async () => stored, removeItem: async () => { stored = null; } },
    'expo-crypto': { randomUUID: require('node:crypto').randomUUID },
    'expo-sqlite': { openDatabaseAsync: async () => sqlite },
    'expo-file-system/legacy': { documentDirectory: 'file:///docs/', makeDirectoryAsync: async () => {}, copyAsync: async () => {}, deleteAsync: async (uri) => { if (failDelete) throw Error('file busy'); deleted.push(uri); } },
    '@react-native-community/netinfo': { fetch: async () => ({ isConnected: connected }) },
  };
  const cache = new Map();
  function load(file) {
    file = path.resolve(file);
    if (cache.has(file)) return cache.get(file).exports;
    if (file.endsWith('/api/captures.ts')) return { CaptureFileError, submitCapture: (...args) => submit(...args) };
    if (file.endsWith('/api/client.ts')) return { ApiError };
    if (file.endsWith('/utils/sync-log.ts')) return { logSync: () => {} };
    const mod = { exports: {} };
    cache.set(file, mod);
    const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText;
    vm.runInNewContext(code, { module: mod, exports: mod.exports,
      require: (name) => mocks[name] ?? (name.startsWith('.') ? load(path.resolve(path.dirname(file), name + '.ts')) : require(name)),
      Date, Math, Promise, Set, Map, Error, console: { error: () => {} } });
    return mod.exports;
  }
  const storage = load('src/storage/capture-outbox.ts');
  const api = { ...storage, ...load('src/features/sync/save-capture.ts'), ...load('src/features/sync/deliver-captures.ts') };
  return { api, db, ApiError, CaptureFileError, deleted, getStored: () => stored, setSubmit: (fn) => { submit = fn; }, setConnected: (value) => { connected = value; }, setFailWrite: (value) => { failWrite = value; }, setFailDelete: (value) => { failDelete = value; } };
}

test('offline preserves saves; acknowledgement removes them using their stable key', async () => {
  const h = harness();
  const entry = await h.api.queueOfflineCapture({ kind: 'text', contentText: 'hello' });
  h.setConnected(false);
  assert.equal((await h.api.syncPendingCaptures()).remaining, 1);
  h.setConnected(true);
  h.setSubmit(async (_, { key }) => { assert.equal(key, entry.key); return { id: 'remote' }; });
  assert.equal((await h.api.syncPendingCaptures()).synced.length, 1);
  assert.equal((await h.api.getPendingCaptures()).length, 0);
  assert.ok(await h.api.getLastAcknowledgedAt());
});

test('last acknowledged save time survives restart and advances only after acknowledgement', async () => {
  const original = harness();
  assert.equal(await original.api.getLastAcknowledgedAt(), null);
  await original.api.queueOfflineCapture({ kind: 'text' });
  original.setSubmit(async () => ({ id: 'remote' }));
  await original.api.syncPendingCaptures();
  const acknowledgedAt = await original.api.getLastAcknowledgedAt();
  assert.ok(acknowledgedAt);

  const restarted = harness(null, original.db);
  assert.equal(await restarted.api.getLastAcknowledgedAt(), acknowledgedAt);
});

test('failed acknowledgement commit does not advance last successful sync time', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'text' });
  h.setSubmit(async () => { h.setFailWrite(true); return { id: 'remote' }; });
  await assert.rejects(h.api.syncPendingCaptures(), /disk full/);
  assert.equal(await h.api.getLastAcknowledgedAt(), null);
  assert.equal((await h.api.getPendingCaptures()).length, 1);
});

test('transient errors persist their reason and back off; manual sync retries immediately', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'text' });
  let calls = 0;
  h.setSubmit(async () => { calls++; throw new h.ApiError('Unavailable', 503); });
  await h.api.syncPendingCaptures();
  assert.equal((await h.api.getPendingCaptures())[0].lastError, 'Unavailable');
  await h.api.syncPendingCaptures();
  assert.equal(calls, 1);
  await h.api.syncPendingCaptures({ force: true });
  assert.equal(calls, 2);
});

test('permanent rejection is retained and excluded from automatic retries', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'text' });
  h.setSubmit(async () => { throw new h.ApiError('Invalid Space', 422); });
  await h.api.syncPendingCaptures();
  assert.equal((await h.api.getPendingCaptures())[0].blocked, true);
});

test('overlapping syncs share one worker and concurrent saves survive reconciliation', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'text' });
  let release;
  h.setSubmit(() => new Promise((resolve) => { release = resolve; }));
  const first = h.api.syncPendingCaptures();
  assert.equal(h.api.syncPendingCaptures(), first);
  while (!release) await new Promise((resolve) => setImmediate(resolve));
  const added = await h.api.queueOfflineCapture({ kind: 'text' });
  release({ id: 'remote' });
  await first;
  assert.equal((await h.api.getPendingCaptures())[0].localId, added.localId);
});

test('disk failure after server success retains attachment copies for idempotent retry', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'file', attachments: [{ kind: 'file', asset: { filename: 'a.txt', mimeType: 'text/plain', uri: 'file:///tmp/a.txt' } }] });
  h.setSubmit(async () => { h.setFailWrite(true); return { id: 'remote' }; });
  await assert.rejects(h.api.syncPendingCaptures(), /disk full/);
  assert.equal(h.deleted.length, 0);
  assert.equal((await h.api.getPendingCaptures()).length, 1);
});

test('completed upload checkpoints survive a failed memory request', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'file' });
  h.setSubmit(async (_, { onUploaded }) => {
    await onUploaded(['asset-1']);
    throw new h.ApiError('Unavailable', 503);
  });
  await h.api.syncPendingCaptures();
  h.setSubmit(async (_, { assetIds }) => { assert.equal(assetIds[0], 'asset-1'); return { id: 'remote' }; });
  await h.api.syncPendingCaptures({ force: true });
  assert.equal((await h.api.getPendingCaptures()).length, 0);
});

test('restart preserves retry metadata, completed uploads and original capture time', async () => {
  const original = harness();
  const entry = await original.api.queueOfflineCapture({ kind: 'text', capturedAt: '2026-10-01T12:00:00Z' });
  original.setSubmit(async (_, { onUploaded }) => {
    await onUploaded(['asset-1']);
    throw new original.ApiError('Try later', 429);
  });
  await original.api.syncPendingCaptures();
  const restarted = harness(null, original.db);
  restarted.setSubmit(async (capture, { key, assetIds }) => {
    assert.equal(capture.capturedAt, '2026-10-01T12:00:00Z');
    assert.equal(key, entry.key);
    assert.equal(assetIds[0], 'asset-1');
    return { id: 'remote' };
  });
  const pending = await restarted.api.getPendingCaptures();
  assert.equal(pending[0].attempts, 1);
  assert.ok(pending[0].retryAt > Date.now());
  await restarted.api.syncPendingCaptures({ force: true });
  assert.equal((await restarted.api.getPendingCaptures()).length, 0);
});

test('legacy queued saves preserve their capture date during sync', async () => {
  const h = harness(JSON.stringify([{ key: 'legacy', localId: '1700000000000-abc', capture: { kind: 'text' } }]));
  h.setSubmit(async (capture) => { assert.equal(capture.capturedAt, new Date(1700000000000).toISOString()); return { id: 'remote' }; });
  await h.api.syncPendingCaptures();
});

test('corrupt queue is surfaced and never overwritten with an empty queue', async () => {
  const h = harness('{broken');
  await assert.rejects(h.api.getPendingCaptures());
  await assert.rejects(h.api.queueOfflineCapture({ kind: 'text' }));
  assert.equal(h.getStored(), '{broken');
});

test('missing local files need attention rather than being retried indefinitely', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'file' });
  let calls = 0;
  h.setSubmit(async () => { calls++; throw new h.CaptureFileError('Missing local file'); });
  await h.api.syncPendingCaptures();
  await h.api.syncPendingCaptures();
  assert.equal(calls, 1);
  assert.equal((await h.api.getPendingCaptures())[0].blocked, true);
});

test('an acknowledgement is delivered even if a later batch item fails persistence', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'text' });
  await h.api.queueOfflineCapture({ kind: 'text' });
  let calls = 0;
  const received = [];
  h.setSubmit(async () => { calls++; if (calls === 2) h.setFailWrite(true); return { id: `remote-${calls}` }; });
  await assert.rejects(h.api.syncPendingCaptures({ onSynced: (item) => received.push(item.memory.id) }), /disk full/);
  assert.deepEqual(received, ['remote-1']);
  assert.equal((await h.api.getPendingCaptures()).length, 1);
});

test('switching off automatic sync stops the worker before the next item', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'text' });
  await h.api.queueOfflineCapture({ kind: 'text' });
  let allowed = true;
  h.setSubmit(async () => { allowed = false; return { id: 'remote' }; });
  const result = await h.api.syncPendingCaptures({ shouldContinue: () => allowed });
  assert.equal(result.synced.length, 1);
  assert.equal(result.remaining, 1);
});

test('observer failure cannot turn a durable save into a failed save', async () => {
  const h = harness();
  const remove = h.api.subscribePendingCaptures(() => { throw Error('observer error'); }, () => {});
  await h.api.queueOfflineCapture({ kind: 'text' });
  remove();
  assert.equal((await h.api.getPendingCaptures()).length, 1);
});

test('migration rolls back all imported rows on a duplicate operation key', async () => {
  const raw = JSON.stringify([
    { key: 'duplicate', localId: '1700000000000-a', capture: { kind: 'text' } },
    { key: 'duplicate', localId: '1700000000001-b', capture: { kind: 'text' } },
  ]);
  const h = harness(raw);
  await assert.rejects(h.api.getPendingCaptures(), /UNIQUE/);
  assert.equal(h.getStored(), raw);
  assert.equal(h.db.prepare('SELECT count(*) AS count FROM capture_outbox').get().count, 0);
  assert.equal(h.db.prepare('SELECT count(*) AS count FROM outbox_migrations').get().count, 0);
});

test('a committed migration marker prevents stale legacy saves from being resurrected', async () => {
  const raw = JSON.stringify([{ key: 'legacy', localId: '1700000000000-a', capture: { kind: 'text' } }]);
  const h = harness(raw);
  await h.api.syncPendingCaptures();
  const restarted = harness(raw, h.db);
  assert.equal((await restarted.api.getPendingCaptures()).length, 0);
  assert.equal(restarted.getStored(), null);
});

test('acknowledged file cleanup resumes after restart without resubmission', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'file', attachments: [{ kind: 'file', asset: { filename: 'a.txt', mimeType: 'text/plain', uri: 'file:///tmp/a.txt' } }] });
  h.setFailDelete(true);
  const result = await h.api.syncPendingCaptures();
  assert.equal(result.synced.length, 1);
  assert.equal(result.remaining, 0);
  assert.equal((await h.api.getAcknowledgedCaptures()).length, 1);
  const restarted = harness(null, h.db);
  restarted.setSubmit(async () => { throw Error('must not resubmit'); });
  await restarted.api.syncPendingCaptures();
  assert.equal(restarted.deleted.length, 1);
  assert.equal((await restarted.api.getAcknowledgedCaptures()).length, 0);
});

test('SQLite file persists an upload checkpoint after closing and reopening the database', async () => {
  const os = require('node:os');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'trove-outbox-'));
  const filename = path.join(dir, 'outbox.db');
  let db = new DatabaseSync(filename);
  try {
    const h = harness('[]', db);
    const entry = await h.api.queueOfflineCapture({ kind: 'text', capturedAt: '2026-10-01T12:00:00Z' });
    h.setSubmit(async (_, { onUploaded }) => { await onUploaded(['asset-one']); throw new h.ApiError('Unavailable', 503); });
    await h.api.syncPendingCaptures();
    db.close();
    db = new DatabaseSync(filename);
    const restarted = harness(null, db);
    restarted.setSubmit(async (capture, options) => {
      assert.equal(options.key, entry.key);
      assert.equal(options.assetIds[0], 'asset-one');
      assert.equal(capture.capturedAt, '2026-10-01T12:00:00Z');
      return { id: 'remote' };
    });
    await restarted.api.syncPendingCaptures({ force: true });
    assert.equal((await restarted.api.getPendingCaptures()).length, 0);
  } finally { db.close(); fs.rmSync(dir, { recursive: true, force: true }); }
});

test('invalid attachment metadata is rejected before committing a capture', async () => {
  const h = harness();
  await assert.rejects(h.api.queueOfflineCapture({ kind: 'file', attachments: [{ kind: 'file', asset: { uri: 'file:///tmp/a', filename: 'a' } }] }));
  assert.equal((await h.api.getPendingCaptures()).length, 0);
});

test('a UI observer failure after acknowledgement cannot cause another upload', async () => {
  const h = harness();
  await h.api.queueOfflineCapture({ kind: 'text' });
  const result = await h.api.syncPendingCaptures({ onSynced: () => { throw Error('render failed'); } });
  assert.equal(result.synced.length, 1);
  h.setSubmit(async () => { throw Error('must not submit again'); });
  assert.equal((await h.api.syncPendingCaptures()).synced.length, 0);
});

test('a corrupted record identity is surfaced without discarding its payload', async () => {
  const h = harness();
  const entry = await h.api.queueOfflineCapture({ kind: 'text' });
  h.db.prepare('UPDATE capture_outbox SET payload = ? WHERE local_id = ?').run(JSON.stringify({ ...entry, key: 'wrong-key' }), entry.localId);
  await assert.rejects(h.api.getPendingCaptures(), /invalid identity/);
  assert.equal(h.db.prepare('SELECT count(*) AS count FROM capture_outbox').get().count, 1);
});

test('presentation read failure after a new commit cannot delete the new attachments', async () => {
  const h = harness();
  const entry = await h.api.queueOfflineCapture({ kind: 'text' });
  h.db.prepare('UPDATE capture_outbox SET payload = ? WHERE local_id = ?').run(JSON.stringify({ ...entry, key: 'wrong-key' }), entry.localId);
  await h.api.queueOfflineCapture({ kind: 'file', attachments: [{ kind: 'file', asset: { filename: 'a.txt', mimeType: 'text/plain', uri: 'file:///tmp/a.txt' } }] });
  assert.equal(h.deleted.length, 0);
  assert.equal(h.db.prepare('SELECT count(*) AS count FROM capture_outbox').get().count, 2);
});
