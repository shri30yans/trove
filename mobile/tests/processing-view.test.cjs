const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const moduleUnderTest = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/features/cloud/processing-view.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { module: moduleUnderTest, exports: moduleUnderTest.exports });
const { processingView } = moduleUnderTest.exports;
const base = { queued: 0, processing: 0, ready: 0, failed: 0, total: 0 };

for (const [name, counts, expected] of [
  ['an empty library is not reported as understood', {}, 'empty'],
  ['a failed job outranks in-progress work', { queued: 2, failed: 1, total: 3 }, 'attention'],
  ['queued work is in progress', { queued: 1, total: 1 }, 'working'],
  ['a running job is in progress', { processing: 1, total: 1 }, 'working'],
  ['all ready means complete', { ready: 4, total: 4 }, 'complete'],
]) {
  test(name, () => assert.equal(processingView({ ...base, ...counts }).state, expected));
}

test('one failure is spelled singular', () => {
  assert.match(processingView({ ...base, failed: 1, total: 1 }).message, /^1 save needs attention/);
});
test('in-progress count covers both queued and running jobs', () => {
  assert.match(processingView({ ...base, queued: 2, processing: 1, total: 3 }).message, /^3 saves are being understood/);
});
test('completion names the understood count', () => {
  assert.match(processingView({ ...base, ready: 3, total: 3 }).message, /^All 3 saves were understood/);
});
