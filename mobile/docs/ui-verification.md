# Mobile UI verification and release

The release gate is native execution plus screenshot review. The automated runner validates a Debug development build; it does not validate production authentication or publish anything.

## Before changing UI

Write the visible invariants and ownership in the work description. For Capture:

- The entire rounded composer and attachment rail remain reachable.
- Focus does not change text height; long notes scroll inside the editor.
- Plus and send controls have large visible glyphs and accessible touch targets.
- Visible clearance separates the composer from the software keyboard.
- Selecting a Space closes its menu and updates only the destination label.
- Opening either menu keeps the keyboard visible; menus are mutually exclusive.
- Leave and re-enter opens the keyboard again.

Use shared tokens and components with matching semantics. Remove competing mechanisms rather than add another offset, timer, or platform override.

## Fast visual iteration

Run npm run preview:web and inspect the same Expo/React Native components in a mobile browser viewport. Check narrow and wider widths, button sizing, text wrapping, full composer borders, destination menus, and Light/Dark/Ultra dark before the native pass. This is a layout check, not native behavior evidence. Do not create a separate HTML copy or add app-side auth/storage fallbacks to make preview work.

For native keyboard issues, use the installed development client with Metro Fast Refresh. Rebuild only when native dependencies or app.json change, or for the final release verification. The first-time toolchain installation is not part of routine visual iteration.

Run the Xcode gate after browser review and before release. Verify native keyboard movement, safe areas, pickers, and every affected shared-component caller there. Viewport rendering cannot replace those checks.

## Xcode setup

Finish installing Xcode, review and accept Apple's license, and complete first-launch setup. Install an iOS simulator runtime from Xcode Settings. Select Xcode as the developer directory. Install Maestro using its official installation instructions. Confirm:

```sh
xcode-select -p
xcodebuild -version
xcrun simctl list devices available
maestro --version
pod --version
```

Create a separate simulator named `Trove Verification` using Xcode's Devices and Simulators window. Do not use a personal simulator or private content. Choose a narrow iPhone for the first pass. Use an English simulator keyboard; the flows assert its visible space key. Disable Simulator's connected hardware keyboard so software-keyboard assertions are meaningful. Install Java 17 or newer for Maestro and CocoaPods for native dependencies; ensure their executables are on PATH.

## Run the gate

Use the real Trove API and a dedicated synthetic user provisioned in the development Supabase Auth project. Sign in through the app's normal sign-in screen. In a terminal in `mobile/`, start this project's Metro:

```sh
npm run start -- --port 8082
```

Use a fresh verification simulator so it has no token from another account. Keep its data synthetic. In another terminal:

```sh
TROVE_SIMULATOR_UDID=<verification-simulator-udid> TROVE_METRO_PORT=8082 npm run verify:ios
```

The command checks prerequisites, runs typecheck/lint/tests, regenerates native configuration from app.json, then builds and installs the native app, runs all Maestro flows, and writes screenshots, a source fingerprint, and JUnit results under `mobile/verification/`. Missing tools, unavailable Metro, failed builds, failed assertions, or source changes during verification exit with failure. Fix the intended path and rerun; do not add skip flags or network workarounds.

Inspect the screenshots, including composer borders, keyboard gap, attachment menu, and Light/Dark/Ultra dark. Record reviewer, observed results, and failures in the generated `review.md`. Automated success leaves visual review pending. Never approve a release from the exit code alone.

For shared keyboard/control changes, also exercise Search, Space creation, and Memory details. Repeat on a larger simulator and a physical device for native pickers, dictation, attachment transfer, and keyboard feel. Use isolated synthetic attachments; do not claim provider delivery from UI tests alone.

## Release checklist

- `npm run check` passes without warnings.
- The current native code passes `npm run verify:ios` and any additional affected-flow tests.
- Current screenshots were inspected and their review recorded; no missing edges, clipped content, inconsistent control sizes, or absent keyboard gap.
- Shared component callers and the supported themes were checked.
- The intended Release configuration builds (`npx expo run:ios --configuration Release --device <udid> --no-bundler`) and its actual sign-in/startup path is verified with the dedicated synthetic Supabase Auth user. Debug builds do not prove Release authentication.
- Applicable physical-device and real API/provider checks pass.
- Report static, simulator, Release-build, live-service, and physical-device results separately. Any required missing evidence blocks release.

There is no publishing command in this repository to intercept. This document and `mobile/AGENTS.md` establish the mandatory gate; any future publishing workflow must depend on these checks and recorded review.

On this workstation, verification tooling is installed separately from the app under `~/.local/share/trove-tools/` and `~/.maestro/`. Use the installed Ruby and Java when invoking the runner:

```sh
export JAVA_HOME="$HOME/.local/share/trove-tools/jdk/Contents/Home"
export PATH="$HOME/.local/share/trove-tools/ruby-runtime/bin:$HOME/.maestro/bin:$PATH"
export SSL_CERT_FILE=/etc/ssl/cert.pem
```

These are development-tool settings; never add them to application code or change application TLS behavior.
