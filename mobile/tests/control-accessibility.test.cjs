const { test } = require('node:test');
const assert = require('node:assert/strict');
const { load, style } = require('./helpers/component-harness.cjs');
const { IconButton } = load('src/components/icon-button.tsx');
const { Button } = load('src/components/button.tsx');
const { Pill } = load('src/components/pill.tsx');

test('every shared control size preserves a minimum 44px touch target', () => {
  for (const variant of ['outline', 'plain', 'tinted']) {
    for (const size of ['small', 'default', 'large']) {
      const resolved = style(IconButton({ icon: 'add', accessibilityLabel: 'Add', onPress() {}, variant, size }));
      assert.ok(resolved.width >= 44 && resolved.height >= 44, `${variant}/${size} icon target is too small`);
    }
  }
  for (const variant of ['primary', 'secondary', 'quiet']) {
    for (const size of ['compact', 'default', 'large']) {
      const resolved = style(Button({ label: 'Save', onPress() {}, variant, size }));
      assert.ok(resolved.minHeight >= 44 && resolved.minWidth >= 44, `${variant}/${size} button target is too small`);
    }
  }
  const pill = style(Pill({ label: 'Space', selected: false, onPress() {} }));
  assert.ok(pill.minHeight >= 44 && pill.minWidth >= 44);
});

test('shared buttons expose busy state consistently to native interaction and accessibility', () => {
  for (const component of [Button, IconButton]) {
    for (const state of [{ loading: true }, { disabled: true }]) {
      const element = component({ label: 'Save', icon: 'add', accessibilityLabel: 'Save', onPress() {}, ...state });
      assert.equal(element.props.disabled, true);
      assert.equal(element.props.accessibilityState.disabled, true);
    }
  }
});
