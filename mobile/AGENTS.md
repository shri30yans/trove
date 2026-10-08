This is an Expo/React Native mobile application. Prioritize mobile-first patterns, performance, and cross-platform compatibility.

## Trove architecture and code principles

Read `../AGENTS.md` and `../.agents/skills/trove-app-building/SKILL.md` for every application implementation, debugging, or review task. The root guidance governs architecture and failure handling; the instructions below govern Expo-specific implementation.

- The app calls only the authenticated Trove API for remote Trove functionality. Storage uploads, media sources, downloads, exports, authentication, and AI all cross this API boundary. Native upload/image/player helpers must not call provider URLs directly.
- Keep network adapters under `src/api/`. Route components compose screens and actions; components render explicit state. Keep domain rules and provider coordination on the server.
- Derive sync counts, status labels, item states, and available actions from one authoritative state model. Never use connectivity as proof of a completed save.
- Preserve local captures before showing success. Local protection is always on. Do not reintroduce an Offline saves toggle or a separate online-only submission path.
- Use the single intended API flow. Do not add silent fallback endpoints, transports, compatibility payloads, mock data, or optional infrastructure modes.
- Required API fields must be validated. Surface invalid configuration or responses; do not hide them using optional chaining, empty data, or a fabricated success message.
- New settings require an explicit user need. Do not turn memory processing, implementation capabilities, or recovery mechanics into arbitrary Profile switches.
- Log safe operation stages and error codes. Verify native behavior using the matching SDK docs and actual runtime evidence. A mocked test or successful bundle is not proof of a device upload.

## Shared UI and React responsibilities

- Inspect `src/components/`, `src/theme.ts`, feature components, and existing hooks before writing new UI. Extend established primitives instead of copying buttons, notices, inputs, cards, or sheets into another screen.
- Put reusable presentation primitives in `src/components/`; keep feature-specific composition and controllers under `src/features/`. Route files in `src/app/` wire navigation and compose these pieces.
- Use typed props, composition, and theme tokens. Keep API calls and persistence out of presentation components. Do not build a universal component with many unrelated modes or flags.
- Derive UI state during rendering from the operation model. Use effects only to synchronize with external systems, and release timers/listeners/tasks on cleanup.
- Preserve accessibility labels/roles, touch targets, loading and disabled states, and keyboard behavior in shared primitives. Check affected screens after changing a shared component.

## Keyboard and focus invariants

- A TextInput keeps native focus after the keyboard is dismissed on navigation away, so `focus()` must never be gated by `isFocused()`. Composer screens own keyboard entry through `src/hooks/use-keyboard-on-screen-focus` (blur → focus on every screen focus); do not add per-screen `autoFocus` props or ad-hoc `useFocusEffect` focus code.
- Opening an in-screen tray (attachments, filters) must not dismiss the keyboard. Do not call `Keyboard.dismiss()` to make room; keep the control inside the keyboard-avoiding layout.
- Bottom docks keep visible clearance above the keyboard. Verify affected composers with the flows in `.maestro/flows/` and report device-verification limits honestly. Read `.agents/skills/trove-mobile-verification/SKILL.md` before claiming any keyboard, theme, or layout behavior works.

## Expo has changed — do not trust your training data

Expo ships breaking changes every SDK release. APIs you remember are likely renamed, moved, or removed. Before writing any code that touches an Expo, EAS, or React Native API:

1. Read the major version of the `expo` package in `package.json`.
2. Fetch the matching versioned docs: `https://docs.expo.dev/versions/v<major>.0.0/`
3. For anything else, fetch https://docs.expo.dev/llms.txt — an index of all Expo docs with corrections to common LLM misconceptions. Follow its links to the specific page you need; never answer from memory.

## Commands

Use `bunx` instead of `npx` if the project uses bun (`bun.lock` present).

```bash
npx expo install <package>  # ALWAYS use instead of npm/yarn/pnpm/bun add — resolves SDK-compatible versions
npx expo start              # start the dev server
npx expo lint               # lint
npx tsc --noEmit            # typecheck
npx expo-doctor             # diagnose dependency and config issues
npx expo install --fix      # fix incompatible package versions
```

Run lint and typecheck before declaring any task done.

## Navigation & Routing

- Use **Expo Router** for all navigation. Routes live in `src/app/` — every file there is a screen, `_layout.tsx` files define navigators. Keep non-route code (components, hooks, utils) outside `src/app/`.
- Import `Link`, `router`, and `useLocalSearchParams` from `expo-router`.
- Docs: https://docs.expo.dev/router/introduction.md

## Building with EAS

Use EAS to build, sign, and submit the app in the cloud (`eas build`, `eas submit`) and to ship over-the-air updates (`eas update`) — no local Xcode or Android Studio required. Run EAS CLI as `bunx eas-cli <command>` in Bun projects, or `npx eas-cli@latest <command>` otherwise; substitute that for bare `eas` in docs examples.
Docs: https://docs.expo.dev/eas/index.md

## Rules

- If `ios/` and `android/` directories do not exist, they are generated (Continuous Native Generation). Never create or edit them by hand — configure native behavior in `app.json` and config plugins.
- Expo Go only includes its bundled native modules. After adding a library with native code, the app needs a development build: `npx expo run:ios|android` locally, or `eas build --profile development`.
- Prefer recommended Expo modules over third-party libraries, and check your available skills before adding dependencies. Docs: https://docs.expo.dev/versions/latest/index.md

## UI ownership and release gate

- Before editing a flow, define its visible invariants and identify the owner of keyboard movement, control sizing, state, and error copy. Reuse components by meaning: a destination selector is not a filter pill.
- ScreenFrame and FormScreen are the only keyboard movement owners, using react-native-keyboard-controller and one root KeyboardProvider. Android uses the library-compatible resize configuration. Do not add screen-level keyboard-height arithmetic, extra avoidance wrappers, or delayed measurement patches. Anchor menus to their actual controls rather than computed screen offsets.
- Keep composer text height independent of focus. The full composer must remain reachable when height is tight; attachments must not shrink away. Show the selected Space once in the action row. Composer controls use the shared large size; preserve at least 44 px touch targets.
- When replacing a mechanism, remove its old styles, state, effects, listeners, props, and imports. Explain remaining platform branches or layout arithmetic with their actual constraint and runtime evidence.
- Run npm run check before delivery. New demonstrated failures get behavioral regression coverage; avoid assertions that merely freeze CSS values.
- Before every mobile release, run npm run verify:ios on a dedicated Xcode simulator with synthetic data. Inspect screenshots and record results in the generated review.md. Static checks, exports, builds, and Maestro assertions alone do not establish visual correctness.
- Shared keyboard/control changes require checking all affected callers: Capture, Search, Space creation, and Memory details. Check narrow screens and Light/Dark/Ultra dark. Verify pickers and physical-device behavior separately where applicable.
- Do not release or describe UI as verified when native tests, screenshot review, or applicable device checks are blocked. Report the concrete blocker. Follow docs/ui-verification.md; do not introduce a bypass flag.

- For visual iteration, use npm run preview:web with the same React Native components at mobile viewport sizes. Review spacing, sizing, wrapping, menus, and themes there before the final native pass. Use Metro Fast Refresh on an installed native client for JS-only edits; rebuild for native configuration/dependency changes and final release verification. Web viewport checks do not establish native keyboard, safe-area, picker, or transfer behavior.

## Shared screen boundary

- Application screens compose `ScreenFrame` for bounded bodies and fixed footers, or `FormScreen` for scrollable forms. These components own safe areas, keyboard movement and header insets. Only this shared module imports library keyboard layout components.
- Put bottom actions in the frame's footer, or in its bounded scrollable body when they belong to the content. Do not overlay them and compensate with estimated bottom padding.
- Do not add keyboard offsets, guessed heights or event listeners to screens. The library owns native keyboard tracking and movement. Do not combine an aware scroll view with another avoiding wrapper.
- Use `ActionSheet` for action menus and confirmations. Keep design rules in `docs/design-system.md` and tokens in `src/theme.ts`.

## Durable capture ownership

- `src/domain/pending-capture.ts` validates persisted capture records. Required capture dates and retry metadata are established at this boundary.
- `src/storage/capture-outbox.ts` is the sole durable queue owner. Use its record operations, never whole-queue read/modify/write or a query cache as the outbox.
- `src/features/sync/` owns file preservation, API delivery, retry policy, status derivation and foreground scheduling in focused modules. WorkspaceProvider reconciles delivered memories; it does not schedule uploads.
- Commit the SQLite acknowledgement before deleting attachments. Keep acknowledged cleanup records until deletion succeeds. Migration imports and its marker must commit in one transaction; corrupt legacy data stays intact.
- Keep SQLite transactions synchronous and short, with no file or network work inside. This avoids unrelated async operations joining a transaction. Do not add another write mutex.

## API and local-storage contracts

- Every JSON request supplies its response schema to `src/api/client.ts`. Never cast an unknown response into a caller-selected type. Schema-derived types are re-exported from `src/types.ts`.
- Keep endpoint projections separate: list, search, updates and full details guarantee different fields. The Memory presentation type does not validate a server response.
- Validate writable bodies, resource IDs and query filters in API adapters. Capability flags are read-only. Partial memory cards cannot acknowledge saves; upload replies must identify the expected asset and transferred byte count.
- Local choices and search history use `src/storage/local-preferences.ts`, with explicit legacy migration. Screens use the shared stored-preference lifecycle and must not parse persisted JSON or swallow storage errors.
- Keep the calendar's themed rendering local. Date selection and API range bounds belong to `src/components/calendar-range.ts`; upper date bounds are exclusive.
