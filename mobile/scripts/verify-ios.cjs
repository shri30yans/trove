#!/usr/bin/env node
const { spawnSync } = require('node:child_process');
const { mkdirSync, writeFileSync, readdirSync, readFileSync } = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');

const project = path.resolve(__dirname, '..');
function sourceFingerprint() {
  const hash = createHash('sha256');
  function add(relative) {
    for (const entry of readdirSync(path.join(project, relative), { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = path.join(relative, entry.name);
      if (entry.isDirectory()) add(file);
      else hash.update(file).update(readFileSync(path.join(project, file)));
    }
  }
  add('src');
  add('.maestro');
  for (const file of ['app.json', 'package.json', 'package-lock.json']) hash.update(file).update(readFileSync(path.join(project, file)));
  return hash.digest('hex');
}
function run(command, args, capture = false) {
  const result = spawnSync(command, args, { cwd: project, encoding: 'utf8', stdio: capture ? 'pipe' : 'inherit' });
  if (result.error || result.status !== 0) throw new Error(`${command} ${args.join(' ')} failed. Resolve the prerequisite or failure before releasing.`);
  return result.stdout?.trim();
}

async function main() {
  const developerDirectory = run('xcode-select', ['-p'], true);
  if (!developerDirectory.endsWith('/Contents/Developer')) {
    throw new Error('Full Xcode must finish installing and be selected with xcode-select. Command Line Tools cannot run simulator verification.');
  }
  run('xcrun', ['xcodebuild', '-version']);
  const devices = JSON.parse(run('xcrun', ['simctl', 'list', 'devices', 'available', '--json'], true));
  const udid = process.env.TROVE_SIMULATOR_UDID;
  const device = Object.values(devices.devices).flat().find((entry) => entry.udid === udid);
  if (!device || !device.name.startsWith('Trove Verification')) {
    throw new Error('Set TROVE_SIMULATOR_UDID to a dedicated simulator named "Trove Verification…". Use synthetic data only; do not run against your personal simulator.');
  }
  run('maestro', ['--version']);
  run('pod', ['--version']);
  const port = process.env.TROVE_METRO_PORT ?? '8081';
  if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) throw new Error('TROVE_METRO_PORT must be a valid TCP port.');
  const metro = await fetch(`http://127.0.0.1:${port}/status`, { signal: AbortSignal.timeout(3000) }).catch(() => null);
  if (!metro?.ok || !(await metro.text()).includes('packager-status:running')) {
    throw new Error('Start this project’s Metro with npm run start in a separate terminal, using a synthetic verification account and the real Trove API.');
  }
  const fingerprint = sourceFingerprint();
  run('npm', ['run', 'check']);
  if (device.state !== 'Booted') run('xcrun', ['simctl', 'boot', udid]);
  run('xcrun', ['simctl', 'bootstatus', udid, '-b']);
  // Hardware keyboards hide the software keyboard and invalidate keyboard evidence.
  run('defaults', ['write', 'com.apple.iphonesimulator', 'ConnectHardwareKeyboard', '-bool', 'false']);
  run('npx', ['expo', 'prebuild', '--platform', 'ios', '--no-install']);
  run('npx', ['expo', 'run:ios', '--device', udid, '--port', port, '--no-bundler']);
  const evidence = path.join(project, 'verification', new Date().toISOString().replace(/[:.]/g, '-'));
  mkdirSync(evidence, { recursive: true });
  run('maestro', ['test', '--device', udid, '--format', 'junit', '--output', path.join(evidence, 'results.xml'), '--test-output-dir', evidence, '.maestro/flows']);
  run('xcrun', ['simctl', 'io', udid, 'screenshot', path.join(evidence, 'final.png')]);
  if (sourceFingerprint() !== fingerprint) throw new Error('Source changed during verification. Preserve the evidence and rerun on the final code.');
  writeFileSync(path.join(evidence, 'review.md'), `# Native verification\n\nSimulator: ${device.name} (${udid})\nSource fingerprint: ${fingerprint}\nBuild: Expo iOS Debug development build\nStatic checks and Maestro: passed\nVisual review: pending\n\nInspect the screenshots for complete composer edges, unchanged text height, keyboard clearance, readable controls, and Space selection in Light, Dark, and Ultra dark. Record the reviewer, observed result, and any failures here. A passing command does not approve a release.\n`);
  console.log(`Native checks passed. Review screenshots in ${evidence} before releasing. Release-build and physical-device checks remain separate (docs/ui-verification.md).`);
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; });
