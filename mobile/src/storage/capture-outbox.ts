import AsyncStorage from '@react-native-async-storage/async-storage';
import { openDatabaseAsync, type SQLiteDatabase } from 'expo-sqlite';
import { parseLegacyQueue, parsePendingCapture, type PendingCapture } from '../domain/pending-capture';
import { normalizeConnectionMessage } from '../api/messages';
import { logSync } from '../utils/sync-log';

const LEGACY_KEY = 'trove.pending-captures.v1';
const listeners = new Map<(items: PendingCapture[]) => void, (error: unknown) => void>();
const syncTimeListeners = new Set<(value: string | null) => void>();
let opening: Promise<SQLiteDatabase> | null = null;

async function openOutbox() {
  const db = await openDatabaseAsync('trove-captures.db');
  try {
    db.execSync(`PRAGMA journal_mode = WAL;
      PRAGMA synchronous = FULL;
      CREATE TABLE IF NOT EXISTS outbox_migrations (name TEXT PRIMARY KEY NOT NULL);
      CREATE TABLE IF NOT EXISTS capture_outbox (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        local_id TEXT NOT NULL UNIQUE,
        operation_key TEXT NOT NULL UNIQUE,
        payload TEXT NOT NULL CHECK(json_valid(payload)),
        state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending', 'acknowledged'))
      );
      CREATE TABLE IF NOT EXISTS sync_metadata (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT NOT NULL
      );`);
    if (!db.getFirstSync('SELECT name FROM outbox_migrations WHERE name = ?', 'async-storage-v1')) {
      const entries = parseLegacyQueue(await AsyncStorage.getItem(LEGACY_KEY));
      // No await inside the transaction: unrelated operations cannot join it.
      db.withTransactionSync(() => {
        for (const entry of [...entries].reverse()) insert(db, entry);
        db.runSync('INSERT INTO outbox_migrations (name) VALUES (?)', 'async-storage-v1');
      });
      logSync('queue.migrated', { count: entries.length });
    }
    // The committed marker prevents an old JSON queue from resurrecting delivered saves.
    await AsyncStorage.removeItem(LEGACY_KEY).catch(() => logSync('queue.legacy-cleanup-failed'));
    return db;
  } catch (error) {
    await db.closeAsync();
    throw error;
  }
}
function database() {
  if (!opening) opening = openOutbox().catch((error: unknown) => { opening = null; throw error; });
  return opening;
}
function insert(db: SQLiteDatabase, entry: PendingCapture) {
  db.runSync('INSERT INTO capture_outbox (local_id, operation_key, payload) VALUES (?, ?, ?)', entry.localId, entry.key, JSON.stringify(entry));
}
type OutboxRow = { local_id: string; operation_key: string; payload: string };
function decode(row: OutboxRow): PendingCapture {
  const entry = parsePendingCapture(JSON.parse(row.payload));
  if (entry.localId !== row.local_id || entry.key !== row.operation_key) {
    throw new Error('A saved item has an invalid identity. Your local data has been kept.');
  }
  return entry.lastError ? { ...entry, lastError: normalizeConnectionMessage(entry.lastError) } : entry;
}
function read(db: SQLiteDatabase, state = 'pending'): PendingCapture[] {
  return db.getAllSync<OutboxRow>('SELECT local_id, operation_key, payload FROM capture_outbox WHERE state = ? ORDER BY sequence DESC', state).map(decode);
}
function notify(items: PendingCapture[]) {
  for (const listener of listeners.keys()) {
    try { listener(items); } catch { logSync('queue.observer-failed'); }
  }
}
function publishCommitted(db: SQLiteDatabase) {
  // A presentation failure must never undo a committed save or delete its files.
  try { notify(read(db)); } catch (error) {
    for (const onError of listeners.values()) {
      try { onError(error); } catch { logSync('queue.observer-failed'); }
    }
  }
}
export async function getPendingCaptures() {
  const items = read(await database());
  notify(items);
  return items;
}
export function subscribePendingCaptures(listener: (items: PendingCapture[]) => void, onError: (error: unknown) => void) {
  listeners.set(listener, onError);
  void database().then((db) => {
    if (listeners.has(listener)) {
      const items = read(db);
      try { listener(items); } catch { logSync('queue.observer-failed'); }
    }
  }).catch((error: unknown) => {
    if (listeners.has(listener)) {
      try { onError(error); } catch { logSync('queue.observer-failed'); }
    }
  });
  return () => { listeners.delete(listener); };
}
export async function insertPendingCapture(entry: PendingCapture) {
  const validated = parsePendingCapture(entry);
  const db = await database();
  insert(db, validated);
  publishCommitted(db);
}
export async function updatePendingCapture(localId: string, patch: Pick<Partial<PendingCapture>, 'assetIds' | 'attempts' | 'retryAt' | 'blocked' | 'lastError'>) {
  const db = await database();
  db.withTransactionSync(() => {
    const row = db.getFirstSync<OutboxRow>('SELECT local_id, operation_key, payload FROM capture_outbox WHERE local_id = ? AND state = ?', localId, 'pending');
    if (!row) throw new Error('The pending save could not be found.');
    const entry = parsePendingCapture({ ...decode(row), ...patch });
    db.runSync('UPDATE capture_outbox SET payload = ? WHERE local_id = ?', JSON.stringify(entry), localId);
  });
  publishCommitted(db);
}
export async function acknowledgeCapture(localId: string) {
  const db = await database();
  const acknowledgedAt = new Date().toISOString();
  db.withTransactionSync(() => {
    const result = db.runSync('UPDATE capture_outbox SET state = ? WHERE local_id = ? AND state = ?', 'acknowledged', localId, 'pending');
    if (result.changes !== 1) throw new Error('The save acknowledgement could not be committed.');
    db.runSync(`INSERT INTO sync_metadata (key, value) VALUES ('last_acknowledged_at', ?)
      ON CONFLICT(key) DO UPDATE SET value = excluded.value
      WHERE excluded.value > sync_metadata.value`, acknowledgedAt);
  });
  publishCommitted(db);
  notifySyncTime(acknowledgedAt);
}
function notifySyncTime(value: string | null) {
  for (const listener of syncTimeListeners) {
    try { listener(value); } catch { logSync('queue.observer-failed'); }
  }
}
export async function getLastAcknowledgedAt() {
  const row = await (await database()).getFirstSync<{ value: string }>(
    "SELECT value FROM sync_metadata WHERE key = 'last_acknowledged_at'",
  );
  return row?.value ?? null;
}
export function subscribeLastAcknowledgedAt(listener: (value: string | null) => void, onError: (error: unknown) => void) {
  syncTimeListeners.add(listener);
  void getLastAcknowledgedAt().then((value) => {
    if (syncTimeListeners.has(listener)) listener(value);
  }).catch((error: unknown) => {
    if (syncTimeListeners.has(listener)) {
      try { onError(error); } catch { logSync('queue.observer-failed'); }
    }
  });
  return () => { syncTimeListeners.delete(listener); };
}
export async function getAcknowledgedCaptures() { return read(await database(), 'acknowledged'); }
export async function finishCaptureCleanup(localId: string) {
  (await database()).runSync('DELETE FROM capture_outbox WHERE local_id = ? AND state = ?', localId, 'acknowledged');
}

export async function clearCaptureOutbox() {
  const db = await database();
  db.withTransactionSync(() => {
    db.runSync('DELETE FROM capture_outbox');
    db.runSync('DELETE FROM sync_metadata');
  });
  publishCommitted(db);
  notifySyncTime(null);
}
