const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// Guards the keyboard/focus invariants from mobile/AGENTS.md. These patterns caused
// the "keyboard never reopens on second entry" bug, which no type/lint check can see.

const SRC = path.join(__dirname, '..', 'src');

function sourceFiles(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...sourceFiles(full));
    else if (/\.tsx?$/.test(entry.name)) found.push(full);
  }
  return found;
}

function scan(pattern, { allow = () => true } = {}) {
  const violations = [];
  for (const file of sourceFiles(SRC)) {
    if (!allow(file)) continue;
    const lines = fs.readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, index) => {
      if (pattern.test(line)) violations.push(`${path.relative(SRC, file)}:${index + 1}: ${line.trim().slice(0, 120)}`);
    });
  }
  return violations;
}

const FOCUS_HOOK = path.join('hooks', 'use-keyboard-on-screen-focus.ts');

test('isFocused() never gates focus decisions', () => {
  // A native input keeps focus after navigation dismisses the keyboard, so an
  // isFocused() guard silently skips refocusing. Zero tolerance.
  const violations = scan(/\.isFocused\s*\(/);
  assert.deepEqual(violations, [], 'Remove isFocused() guards; composer screens use useKeyboardOnScreenFocus.');
});

test('imperative .focus() lives only in the keyboard hook', () => {
  const violations = scan(/\.focus\s*\(\s*\)/, { allow: (file) => path.relative(SRC, file) !== FOCUS_HOOK });
  assert.deepEqual(violations, [], 'Route keyboard entry through src/hooks/use-keyboard-on-screen-focus instead of ad-hoc focus() calls.');
});

test('screen and route files carry no autoFocus props', () => {
  // autoFocus only fires on first mount, which is exactly the stale-state trap on re-entry.
  // Sheets/modals (mounted per open) may still use it.
  const violations = scan(/autoFocus/, {
    allow: (file) => {
      const rel = path.relative(SRC, file);
      return rel.startsWith(path.join('app', '')) || /-screen\.tsx$/.test(rel);
    },
  });
  assert.deepEqual(violations, [], 'Screens use useKeyboardOnScreenFocus; autoFocus props on screens prove wrong on second entry.');
});

test('capture flow never dismisses the keyboard', () => {
  const violations = scan(/Keyboard\.dismiss/, {
    allow: (file) => path.relative(SRC, file).startsWith(`features${path.sep}capture${path.sep}`),
  });
  assert.deepEqual(violations, [], 'Attachment trays must open inside the keyboard-avoiding layout, not by dismissing the keyboard.');
});

test('Android uses the library-compatible resize mode', () => {
  const config = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'app.json'), 'utf8'));
  assert.equal(config.expo.android.softwareKeyboardLayoutMode, 'resize');
});

test('keyboard movement belongs to the shared screen components', () => {
  const violations = scan(/KeyboardAvoidingView|KeyboardAwareScrollView|Keyboard\.addListener|Keyboard\.metrics|keyboardLift|keyboardVerticalOffset/, {
    allow: (file) => path.relative(SRC, file) !== path.join('components', 'screen-frame.tsx'),
  });
  assert.deepEqual(violations, [], 'Use ScreenFrame or FormScreen; do not add competing keyboard adjustments.');
});

test('keyboard provider belongs to the root layout', () => {
  const violations = scan(/KeyboardProvider/, {
    allow: (file) => path.relative(SRC, file) !== path.join('app', '_layout.tsx'),
  });
  assert.deepEqual(violations, [], 'Keep one root keyboard provider.');
  assert.match(fs.readFileSync(path.join(SRC, 'app/_layout.tsx'), 'utf8'), /<KeyboardProvider>/);
});

test('native flows do not use the unsupported keyboard and screenshot commands', () => {
  const flows = path.join(__dirname, '..', '.maestro', 'flows');
  for (const file of fs.readdirSync(flows).filter((name) => name.endsWith('.yaml'))) {
    const source = fs.readFileSync(path.join(flows, file), 'utf8');
    assert.doesNotMatch(source, /isKeyboardVisible:|^- screenshot:/m, `${file}: use supported Maestro assertions and takeScreenshot.`);
  }
});

test('editable screens use the shared screen boundary', () => {
  for (const file of ['features/capture/capture-screen.tsx', 'features/search/search-screen.tsx', 'features/spaces/space-sheet.tsx', 'features/memories/memory-detail-sheet.tsx']) {
    assert.match(fs.readFileSync(path.join(SRC, file), 'utf8'), /<(?:ScreenFrame|FormScreen)[\s>]/, `${file}: use the common safe-area and keyboard boundary.`);
  }
});
