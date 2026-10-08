const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// Guards the colour invariants behind the create control and the dark palettes. Both
// defects below were invisible to typecheck and lint: a create button filled with a
// low-chroma tint role sank into the true-black page, and a shadowColour taken from a
// theme role rendered a light halo because `deep` is a near-white chip on dark palettes.

const SRC = path.join(__dirname, '..', 'src');
const THEME = fs.readFileSync(path.join(SRC, 'theme.ts'), 'utf8');

function hexToRgb(hex) {
  const value = hex.slice(1);
  return [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16));
}

function luminance(hex) {
  const channels = hexToRgb(hex).map((raw) => {
    const c = raw / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

/** Palettes as declared in theme.ts: name -> semantic role -> hex colour. */
function readPalettes() {
  const palettes = new Map();
  for (const block of THEME.matchAll(/const (\w+Colors)(?:: Palette)? = \{([\s\S]*?)\n\};/g)) {
    const roles = {};
    for (const entry of block[2].matchAll(/(\w+): '(#[0-9A-Fa-f]{6})'/g)) roles[entry[1]] = entry[2].toUpperCase();
    palettes.set(block[1].replace('Colors', ''), roles);
  }
  return palettes;
}

/** Theme id -> mode, read from the `themes` record so dark palettes can be checked as dark. */
function readModes() {
  const modes = {};
  for (const entry of THEME.matchAll(/^ {2}(\w+): \{ label: '[^']+', mode: '(light|dark)', colors: (\w+) \},$/gm)) {
    modes[entry[1]] = entry[2];
  }
  return modes;
}

function sourceFiles(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...sourceFiles(full));
    else if (/\.tsx?$/.test(entry.name)) found.push(full);
  }
  return found;
}

const palettes = readPalettes();
const modes = readModes();
const FAB_STYLE = fs.readFileSync(path.join(SRC, 'components', 'create-fab.tsx'), 'utf8');

test('every palette declares a create-control action pair', () => {
  assert.ok(palettes.size >= 15, `expected every palette to parse, found ${palettes.size}`);
  const missing = [];
  for (const [name, roles] of palettes) {
    for (const role of ['action', 'onAction', 'deep', 'background']) {
      if (!roles[role]) missing.push(`${name}.${role}`);
    }
  }
  assert.deepEqual(missing, [], 'action/onAction must be declared on every palette, not defaulted per screen.');
});

test('the action label is readable and the borderless control is findable on its own page', () => {
  const failures = [];
  for (const [name, roles] of palettes) {
    const label = contrast(roles.action, roles.onAction);
    // The control has no border by request, so the fill alone must mark where it ends.
    // WCAG 1.4.11 asks for 3:1; Ultra dark trades that for the shared selected-pill violet and
    // stays a real tonal shape, so it has its own floor rather than leaving the test silent.
    const edge = contrast(roles.action, roles.background);
    const floor = name === 'ultra' ? 1.9 : 3;
    const fromDock = contrast(roles.action, roles.deep);
    if (label < 4.5) failures.push(`${name}: action/onAction ${label.toFixed(2)}:1 (needs 4.5:1 for the Create label)`);
    if (edge < floor) failures.push(`${name}: create fill ${edge.toFixed(2)}:1 on the page (needs ${floor}:1 or it disappears without a border)`);
    if (fromDock < 1.5) failures.push(`${name}: create fill ${fromDock.toFixed(2)}:1 against the dock (Create must not merge with it)`);
  }
  assert.deepEqual(failures, [], 'Adjust the palette so the create control keeps its own contrast contract.');
});

test('the true-black create control is the selected nav pill, unbordered', () => {
  // The user asked for the button to match the pill Home takes when selected, to reuse colours
  // already in the palette, and to have no boundary. Encoding all three keeps a later re-ramp
  // from quietly reintroducing an invented hex or a hairline.
  const ultra = palettes.get('ultra');
  assert.ok(ultra, 'ultra palette failed to parse');
  assert.equal(ultra.action, ultra.lavender, 'create fill must stay the selected-pill violet');
  assert.equal(ultra.onAction, ultra.foreground, 'create label must stay the body ink used on that pill');
  assert.ok(!/borderWidth|borderColor/.test(FAB_STYLE), 'CreateFab must not draw its own border');
});

test('body text and the dock ink survive a palette re-ramp', () => {
  // Dimming `deep` or `foreground` for glare reasons is exactly how a dark theme loses
  // legibility, and no type or lint check can see it. These are the pairs real text uses.
  const textPairs = [
    ['foreground on background', 'foreground', 'background'],
    ['foreground on surface', 'foreground', 'surface'],
    ['dock ink (surface on deep)', 'surface', 'deep'],
    ['muted on surface', 'muted', 'surface'],
  ];
  const failures = [];
  for (const [name, roles] of palettes) {
    for (const [label, ink, fill] of textPairs) {
      const ratio = contrast(roles[ink], roles[fill]);
      if (ratio < 4.5) failures.push(`${name}: ${label} ${ratio.toFixed(2)}:1`);
    }
    // Chips that carry text or glyphs: the tint must stay dark under the foreground ink.
    for (const tint of ['lavender', 'icyBlue', 'thistle', 'petal', 'skyBlue']) {
      const ratio = contrast(roles.foreground, roles[tint]);
      if (ratio < 3) failures.push(`${name}: foreground on ${tint} ${ratio.toFixed(2)}:1 (needs 3:1 for glyphs)`);
    }
  }
  assert.deepEqual(failures, [], 'Raise the ink or lower the fill so these pairs clear their thresholds.');
});

test('dark palettes step lighter with elevation', () => {
  assert.ok(Object.keys(modes).length >= 15, `expected every theme mode to parse, found ${Object.keys(modes).length}`);
  const failures = [];
  let checked = 0;
  for (const [name, roles] of palettes) {
    if (modes[name] !== 'dark') continue;
    checked += 1;
    const { background, surface, surfacePressed } = roles;
    if (!(luminance(background) < luminance(surface) && luminance(surface) < luminance(surfacePressed))) {
      failures.push(`${name}: ${background} -> ${surface} -> ${surfacePressed} is not a rising ramp`);
    }
  }
  assert.ok(checked >= 8, `dark palettes were skipped; only ${checked} matched a declared mode`);
  assert.deepEqual(failures, [], 'On dark themes depth comes from a lighter surface, not from shadows.');
});

test('no component takes its shadow colour from a theme role', () => {
  // `deep` is a near-white chip on dark palettes, so as a shadow colour it draws a halo.
  const violations = [];
  for (const file of sourceFiles(SRC)) {
    fs.readFileSync(file, 'utf8').split('\n').forEach((line, index) => {
      if (/shadowColor:\s*(colors|palette)\./.test(line)) {
        violations.push(`${path.relative(SRC, file)}:${index + 1}: ${line.trim().slice(0, 120)}`);
      }
    });
  }
  assert.deepEqual(violations, [], 'Floating elevation must spread the shared shadow.float token.');
});
