---
name: trove-app-building
description: Implement, debug, or review Trove mobile and backend application flows using the repository's API boundary, declarative state handling, and delivery verification requirements. Use for Trove app code and architecture, not unrelated artifacts or other projects.
---

# Trove app building

Read the repository root `AGENTS.md` before working. For mobile changes, also read `mobile/AGENTS.md`. These are the authoritative engineering rules; this skill supplies the working method.

## Establish the flow

Describe the intended user action and its completion condition. Trace the current path from the screen through `mobile/src/api/` into the current Python routes, domain code, database, and provider adapter. Identify which component owns each decision and which durable record proves completion. Use `app/`, not `legacy/`, to establish current server behavior.

The client calls the authenticated Trove API for all remote Trove functionality. Check indirect calls too: image sources, video/audio players, WebViews, download helpers, export links, authentication SDKs, signed URLs, and background tasks. Keep external integrations behind server adapters. Device-local files and persistence are client responsibilities.

Define required request/response fields and explicit states for the changed operation. Put state transitions in one focused owner and derive labels, counts, button availability, and item detail state from that model. Keep screens declarative. Do not add a separate preference or capture mode to avoid deciding the correct behavior.

## Implement one path

Change the intended API flow directly. Remove obsolete branches and callers in the touched flow. Do not introduce an alternate transport, provider, capability mode, compatibility fallback, or default endpoint when configuration is missing. If a contract changes, update the server and all affected clients together.

Check every error branch for a concrete consequence: retry the same identified operation, retain durable work and require attention, or fail the operation visibly. Catch only where that decision belongs. Preserve the difference between saved locally, confirmed remotely, and processed downstream.

For capture/sync work, read `mobile/docs/sync-design.md` as implementation context, then verify it against current code and runtime evidence. Its historical discussion is not permission to preserve a prohibited architecture or infrastructure workaround.

## Reuse before adding code

Inspect the existing shared components, theme, feature hooks, API adapters, and backend domain functions that serve the touched flow. Identify the existing owner of each repeated responsibility before creating a new one.

Reuse established primitives and shared behavior. Extract genuinely repeated patterns into a focused component or function with clear typed inputs; keep feature-specific composition local. Prefer composition over a component with many optional modes. Use shared theme tokens rather than repeat styling constants.

Review state ownership and side effects: rendering derives from state, controllers coordinate operations, API adapters handle transport, and backend domain functions own business rules. Remove redundant state/effect chains, unused props, obsolete branches, and duplicated validation/formatting in the changed flow. Avoid type assertions that pretend unvalidated responses are valid.

For shared UI changes, inspect affected callers and verify consistent accessibility, keyboard/touch behavior, and loading/error/disabled states. Reuse must simplify the flow without introducing hidden coupling or a speculative framework.

## Debug with evidence

Follow the actual failing operation using safe stage logs. For uploads, establish whether allocation, device transfer, provider write, completion verification, or memory acknowledgement failed. URL signing/allocation alone proves neither storage authentication nor successful delivery.

Test network reachability and credential validity separately. Report the concrete failing service and status/error code. Do not repair infrastructure by weakening security or adding a hidden app-side routing workaround. Keep keys in server-local configuration and out of logs, client bundles, command output, and shared artifacts.

Load the repository Supabase skill for Supabase integration work and its Postgres best-practices skill before SQL/schema work. Apply their provider-specific guidance within Trove's server-only integration boundary.

## Verify the observable result

Use meaningful regression tests for the changed invariants: failure classification, ownership/limits, restart recovery, concurrency, idempotency, and acknowledgement ordering as relevant. Avoid tests that merely duplicate implementation or check wording.

For integration changes, exercise the actual API and provider with isolated synthetic data. Verify the stored file or memory and retry identity, not just an HTTP allocation response. Confirm rejected requests cannot modify another owner's data. Verify the UI/device result when the environment permits; report any remaining access limitation explicitly.

Run the root `AGENTS.md` checks for changed code. Review the touched flow for direct external calls, contradictory state, swallowed failures, unused branches, and unsolicited settings before declaring completion. Report the finding, the implemented correction, verification, and any remaining concrete blocker.
