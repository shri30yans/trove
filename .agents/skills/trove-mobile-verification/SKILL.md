---
name: trove-mobile-verification
description: Produce runtime evidence for Trove mobile keyboard, navigation, theme, and layout behavior using an iOS simulator and Maestro flows. Use whenever a change touches keyboard/focus behavior, bottom docks, screen entry/exit, theming, or any UI claim that static checks cannot prove.
---

# Trove mobile verification

Static checks (typecheck, lint, unit tests) cannot prove keyboard, focus, or layout behavior. Treat a mobile UI claim as unverified until this loop produces runtime evidence, and state which layer was verified: unit, static, simulator, or physical device.

## Harness status check

Run these before promising device evidence; report the exact missing piece as the blocker instead of substituting a weaker check:

```bash
xcode-select -p                 # must be /Applications/Xcode.app/... for simctl
xcrun simctl list devices available
command -v maestro
```

Discover the current installation each time. Xcode.appdownload is an unfinished download, not an installed toolchain. Confirm Xcode is selected, its license and first-launch setup are complete, an iOS simulator runtime is available, and Maestro runs.

## Lightweight tiers (no Xcode required)

1. **Static invariants — always on.** `mobile/tests/ui-invariants.test.cjs` (runs inside `npm test`) bans the keyboard bug class outright: `isFocused()` guards, ad-hoc `.focus()` outside the hook, `autoFocus` on screens/routes, and `Keyboard.dismiss` in the capture flow. When a new runtime bug is caught by a human, add its pattern as a scan rule here the same day.
2. **Expo Go on the user's iPhone — real keyboard physics, manual.** `npm run start:expo-go` from `mobile/`, user scans the QR (same LAN or `--tunnel`). All native deps ship in Expo Go SDK 57; `expo-share-intent` self-disables via `Constants.executionEnvironment === 'storeClient'`, so boot is expected but confirm it. Hand the user the keyboard checklist below; their screenshot or report is device evidence. Metro console output (`npx expo start` logs) shows app-side errors while they tap.
3. **Android automation — no Xcode.** With any Android device on USB: `brew install android-platform-tools` + Maestro, then run the `.maestro/flows/` against `host.exp.exponent` (Expo Go) or the debug build. This automates the same assertions the simulator tier would.

The full simulator loop below remains the preferred tier once Xcode exists.

## One-time setup (after Xcode exists)

```bash
sudo xcode-select -s /Applications/Xcode.app
xcrun simctl boot "iPhone 16" || xcrun simctl create "iPhone 16" "iPhone 16"
cd mobile && npx expo run:ios   # builds + installs the dev build on the booted simulator
curl -Ls https://get.maestro.mobile.dev | bash   # Maestro CLI
```

Maestro drives the dev build with appId `com.trove.memory`. Flows assume a signed-in dev-auth session and tap by visible label/accessibility label.

## Release verification

Every mobile release requires npm run check, npm run verify:ios, and recorded screenshot review. Follow mobile/docs/ui-verification.md with synthetic data. Missing prerequisites block release; never substitute a bundle export or skip native verification. Shared components require checking all affected callers. Distinguish Debug simulator evidence, Release build validation, and physical-device evidence.

## Verification loop

1. Make the change; run `npm run typecheck && npm run lint` from `mobile/`.
2. Rebuild/relaunch: `npx expo run:ios` (or reload Metro if only JS changed).
3. Run the relevant flow: `maestro test .maestro/flows/<flow>.yaml` from `mobile/`.
4. Capture visuals: `xcrun simctl io booted screenshot /tmp/trove.png`, then Read the image and inspect spacing, theme, and keyboard clearance directly.
5. On failure, reproduce the smallest interaction sequence, add it as a step in the flow, fix, and rerun until green. Keep new regression flows in `mobile/.maestro/flows/`.

## Keyboard invariants (the class of bug that motivated this skill)

- A focused TextInput can keep native focus after the keyboard is dismissed on navigation away. Never gate `focus()` behind `isFocused()`; composer screens use `src/hooks/use-keyboard-on-screen-focus` and no `autoFocus` props.
- Every screen with a composer must pass: first entry raises the keyboard; leave and re-enter raises it again; opening the attachment tray keeps it up; bottom docks keep visible clearance above the keyboard.
- When fixing a keyboard/focus bug, encode the exact reproduce sequence (open → dismiss → leave → re-enter) as Maestro steps with supported `assertVisible: "space"` assertions on an English iOS software keyboard before declaring it fixed.

## Evidence rules

- A passing bundle export, health endpoint, or mock is not device behavior; say what could not be verified and why.
- Physical-device-only behaviors (native pickers, dictation, haptics, keyboard heights across devices) still require a real phone; the simulator proves structure and state, not feel.
