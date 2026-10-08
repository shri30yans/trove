const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { embeddingState } = createLoader()('src/domain/embedding-state.ts');
const settings = { resurfacingEnabled: false, resurfacingCadence: 'weekly', embeddingsEnabled: true, embeddingsAvailable: true };
test('missing preferences mean loading, not disabled capabilities', () => assert.equal(embeddingState(null, null).state, 'loading'));
test('a failed preference read is visible even when old data exists', () => assert.equal(embeddingState(settings, 'Unavailable').state, 'error'));
test('disabled account settings and unavailable services are distinct states', () => {
  assert.equal(embeddingState({ ...settings, embeddingsEnabled: false }, null).state, 'disabled');
  assert.equal(embeddingState({ ...settings, embeddingsAvailable: false }, null).state, 'unavailable');
  assert.equal(embeddingState(settings, null).state, 'available');
});
