# Trove application engineering

These rules apply to the entire repository. For application implementation, debugging, or review, also read `.agents/skills/trove-app-building/SKILL.md`. Mobile-specific Expo instructions live in `mobile/AGENTS.md`.

## Architecture boundary

The only remote service the app may call for Trove functionality is the authenticated Trove API.

- Route uploads, downloads, media playback, thumbnails, exports, authentication, search, and AI requests through the API. A remote URL consumed by an image/video component is a network call too.
- Keep Supabase, S3, database, identity-provider, AI-provider, and other integration clients and credentials on the backend. Do not return provider URLs or signed storage URLs for the app to consume.
- The backend authenticates requests, enforces ownership and limits, coordinates persistence, and translates provider failures into a stable API contract. The client owns presentation and device-local capture/persistence.
- Use the current Python implementation in `app/` and the mobile client in `mobile/src/` as the implementation source of truth. `legacy/` is historical; it does not establish the current contract.

## Simple, declarative flows

- Define the user-visible outcome, API contract, state transitions, and completion condition before changing a flow.
- Use one authoritative state model and derive UI from it. Represent mutually exclusive states explicitly; avoid combinations of independent booleans that can contradict each other.
- Keep domain decisions in the backend, transport in API adapters, lifecycle coordination in a focused controller, and rendering in components. Screens must not orchestrate provider integrations.
- Keep the intended flow linear and explicit. Use required contract fields where the operation requires them. Represent meaningful absent data deliberately; do not hide missing contract fields behind optional chaining or fabricated defaults.
- Add abstractions only when they express an actual domain boundary or remove meaningful duplication. Avoid speculative generalization, wrappers that merely rename calls, and competing implementations.
- Keep settings limited to user-requested, meaningful choices. Do not expose implementation details as switches. Local save protection is mandatory, not an optional capture mode.

## Reuse and maintainability

- Inspect existing components, hooks, domain functions, and adapters before adding another implementation. Reuse or extend the established owner of the behavior.
- Share repeated UI patterns and behavior: buttons, form fields, status notices, loading/empty/error states, cards, sheets, and list items. Keep feature-specific composition in its feature; promote a component to shared code when its semantics are actually shared.
- Prefer small, composable components with clear typed props. Avoid giant configurable components, boolean-prop combinations, duplicated screen markup, and components that combine rendering, networking, persistence, and domain rules.
- Use the established theme and design tokens for color, spacing, typography, radii, and interaction states. Extend missing tokens centrally rather than scatter new magic values across screens.
- Keep a single implementation of shared validation, formatting, error translation, and operation coordination. Do not duplicate business rules across endpoints or screens.
- Name functions, variables, and modules after domain meaning and responsibility. Keep functions focused, inputs/outputs explicit, and side effects at defined boundaries. Prefer straightforward composition over deep nesting or clever control flow.
- Derive values from authoritative state instead of synchronizing redundant state through effects. Use effects for external subscriptions and resource lifecycles, with cleanup; do not use them to chain business decisions that belong in an action/controller.
- Keep types precise. Validate untrusted data at boundaries; avoid `any`, type assertions that bypass validation, and non-null assertions that hide invalid state.
- Remove dead code, unused props/imports, obsolete flags, and duplicate paths in the changed flow. Write comments to explain a real constraint or invariant, not to narrate obvious code.
- Shared components must preserve accessibility, disabled/busy behavior, touch targets, and cross-platform behavior. Verify the affected callers when shared behavior changes; do not trade consistency for a local patch.
- Keep work scoped to the requested flow. Improve its structure as needed, without speculative frameworks, unnecessary dependencies, or unrelated rewrites.

## Failure handling

- No silent fallbacks, alternate providers/transports, local-to-remote mode switching, compatibility branches, mock data, or fabricated success states. Fix the intended path; surface its failure if it cannot complete.
- Retry the same operation only when failure is transient, preserving its identity and checkpoints. A retry is not an alternate execution path. Bound retry timing and distinguish failures requiring user/admin action.
- Validate configuration and external response contracts explicitly. Missing credentials, invalid endpoints, or unsupported capabilities must produce an actionable state; do not select a hidden default service or return apparent success.
- Never weaken TLS, authentication, ownership checks, or limits to get a test passing. Do not embed DNS overrides, development proxies, or environment-specific network workarounds in application logic. Treat network and credential failures as infrastructure problems with explicit configuration.
- Catch errors where a recovery decision or API/UI translation is made. Preserve useful causes. Best-effort ancillary cleanup may fail without reversing a confirmed save; record that failure rather than changing the operation's result.

## Data integrity and observability

- Distinguish local durability, server acknowledgement, and downstream processing. Connectivity is not evidence of synchronization.
- Persist local captures before reporting a successful local save. Persist acknowledgement before releasing retryable data or deleting local attachments. Use stable idempotency keys and preserve capture timestamps.
- Serialize queue mutations and reconcile each confirmed item. Late reads must not resurrect completed work or erase newly confirmed saves.
- Log operation IDs, stages, attempts, elapsed time, status/error codes, and acknowledgement outcomes. Exclude content, filenames, credentials, tokens, signed URLs, and response bodies that may contain private data.
- Diagnose the actual failing boundary with runtime evidence. Do not conclude that a device flow works because the API health endpoint, URL allocation, mocks, or a bundle export succeeds.

## Verification and completion

Run checks appropriate to changed code:

- Mobile: `npm run check` from `mobile/` (typecheck, lint with zero warnings, and regression tests). Before mobile release, also run `npm run verify:ios` on a dedicated Xcode simulator and record screenshot review as specified in `mobile/docs/ui-verification.md`. Missing native or visual evidence blocks release.
- Backend: Ruff, mypy, and relevant pytest cases through the repository's `.venv` commands or `make check`.
- Integration changes: verify the real path through authorization, transfer, provider persistence verification, acknowledgement, and safe retry using isolated synthetic data. Also check rejection/ownership behavior. Never use private user content as a test fixture.

State separately what was verified in unit tests, against live services, and on the actual device. An export is not a native build or a device test. If required credentials or infrastructure are unavailable, preserve work, report the exact blocker, and do not claim end-to-end completion.
