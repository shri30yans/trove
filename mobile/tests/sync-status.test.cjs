const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const moduleUnderTest = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/features/sync/sync-status.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { module: moduleUnderTest, exports: moduleUnderTest.exports });
const { getSyncStatus } = moduleUnderTest.exports;
const base = { ready: true, pending: [], uploadingId: null, online: true, automaticSync: true, error: null };
const pending = [{ localId: 'one', capture: { kind: 'text' }, key: 'one' }];
for (const [name, values, expected] of [
  ['initial load cannot report synced', { ready: false }, 'loading'],
  ['connectivity does not prove backup completion', { pending }, 'retrying'],
  ['no unacknowledged local saves means complete', {}, 'complete'],
  ['offline retains already confirmed backup status', { online: false }, 'complete'],
  ['offline with unconfirmed saves waits for connection', { online: false, pending }, 'offline'],
  ['manual sync can upload with automatic sync off', { automaticSync: false, pending, uploadingId: 'local-one' }, 'uploading'],
  ['disabled automatic sync is paused', { automaticSync: false, pending }, 'paused'],
  ['permanent failure is actionable', { pending: [{ ...pending[0], blocked: true, lastError: 'Too large' }] }, 'blocked'],
  ['transient failure will retry', { pending: [{ ...pending[0], lastError: 'Unavailable' }] }, 'retrying'],
  ['storage failure cannot report synced', { error: 'Could not read local queue' }, 'blocked'],
]) {
  test(name, () => assert.equal(getSyncStatus({ ...base, ...values }).state, expected));
}

test('permanent manual-sync failure remains actionable when automatic sync is off', () => {
  const status = getSyncStatus({ ...base, automaticSync: false, pending: [{ ...pending[0], blocked: true, lastError: 'Sign in again.' }] });
  assert.equal(status.state, 'blocked');
  assert.match(status.message, /Sign in again/);
  assert.equal(status.detail, 'Sign in again.');
});
test('permanent rejection is still visible after losing connectivity', () => {
  const status = getSyncStatus({ ...base, online: false, pending: [{ ...pending[0], blocked: true, lastError: 'Too large' }] });
  assert.equal(status.state, 'blocked');
});
test('failed manual sync does not promise automatic retry when disabled', () => {
  const status = getSyncStatus({ ...base, automaticSync: false, pending: [{ ...pending[0], lastError: 'Could not connect to Trove.' }] });
  assert.equal(status.state, 'paused');
  assert.doesNotMatch(status.message, /will retry|will try again/i);
});
