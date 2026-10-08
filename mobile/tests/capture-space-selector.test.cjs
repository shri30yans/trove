const { test } = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./helpers/component-harness.cjs');
const { CaptureSpaceSelector } = load('src/features/capture/capture-space-selector.tsx');
const spaces = [{ id: 'synthetic-space', name: 'Synthetic Space' }];
function render(overrides = {}) {
  return CaptureSpaceSelector({ spaces, selectedId: 'synthetic-space', expanded: false, disabled: false, onToggle() {}, onSelect() {}, ...overrides });
}

test('collapsed destination shows the selected name without retaining a choices panel', () => {
  const [trigger, menu] = render().props.children;
  assert.equal(trigger.props.children[0].props.children, 'Synthetic Space');
  assert.equal(menu, false);
  assert.equal(trigger.props.accessibilityState.expanded, false);
});

test('Space choices report the exact destination including explicit no-Space selection', () => {
  const selected = [];
  const [, menu] = render({ expanded: true, onSelect: (id) => selected.push(id) }).props.children;
  const [all, space] = menu.props.children;
  all.props.onPress();
  space.props.onPress();
  assert.deepEqual(selected, [null, 'synthetic-space']);
  assert.equal(space.props.accessibilityState.selected, true);
});

test('a busy capture disables the destination trigger and every option', () => {
  const [trigger, menu] = render({ disabled: true, expanded: true }).props.children;
  assert.equal(trigger.props.disabled, true);
  assert.ok(menu.props.children.every((option) => option.props.disabled && option.props.accessibilityState.disabled));
});
