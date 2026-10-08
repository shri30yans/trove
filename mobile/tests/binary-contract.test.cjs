const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { validateBinaryResponse } = createLoader()('src/api/schemas/binary.ts');
const response = { status: 200, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Content-Length': '5' } };
test('binary metadata normalizes header case and MIME parameters', () => {
  assert.doesNotThrow(() => validateBinaryResponse(response, 5, 'text/plain'));
});
test('binary metadata rejects wrong type, truncated bytes and invalid declared sizes', () => {
  assert.throws(() => validateBinaryResponse(response, 4, 'text/plain'));
  assert.throws(() => validateBinaryResponse(response, 5, 'application/zip'));
  for (const length of ['NaN', '-1', '5.1', '9007199254740992']) {
    assert.throws(() => validateBinaryResponse({ status: 200, headers: { 'content-type': 'text/plain', 'content-length': length } }, 5, 'text/plain'));
  }
});
