---
name: trove-app-building
description: Implement, debug, or review Trove mobile and backend application flows using the repository's API boundary, declarative state handling, and delivery verification requirements. Use for Trove app code and architecture, not unrelated artifacts or other projects.
---

# Trove app building

Read the repository root `AGENTS.md` before working. For mobile changes, also read `mobile/AGENTS.md`. These are the authoritative engineering rules; this skill supplies the working method.

## Establish the flow

Describe the intended user action and its completion condition. Trace the current path from the screen through `mobile/src/api/` into the Python routes, domain code, database, and provider adapter. Identify which component owns each decision and which durable record proves completion. Use `app/` to establish server behavior.

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

### Auth release checklist

Auth has three independently deployed pieces: mobile screens/deep links, Trove API routes, and Supabase Auth redirects/templates. Trace all three; passing mobile tests or seeing the route in `app/routes/auth.py` does not prove the active API has it.

- Before release, compare `git rev-parse --short <intended-ref>` with `heroku releases --app trove --num 3`. Never use `heroku releases:info` or print Heroku config: release detail output may include the full config-var values.
- After release, run `make auth-release-check`. Its invalid-body probes must return the expected structured 400 for sign-up, resend, and confirmation; a missing route often returns a plain 404 and the client may translate it to an unrelated generic not-found message.
- Signup and resend must redirect to the HTTPS Trove confirmation landing page derived from the configured public API URL. That page is the browser fallback and offers a validated `trove://confirm-email` handoff. Keep the app scheme in `mobile/app.json` and allow both exact redirect URLs in Supabase.
- The mobile callback must validate and persist the Supabase signup session, and the fallback page must tell users to return to Trove and sign in if the app handoff is unavailable. Release probes must verify the landing page.
- Check Supabase email templates for the Trove logo asset URL and required `{{ .ConfirmationURL }}` placeholder. Apply template edits through the Management API, preserve existing SMTP settings, and read back only the changed subject/template fields. Never print the full auth config or access token.
- For real end-to-end verification, use a dedicated synthetic account and inbox; record whether delivery, provider verification, the app deep link, and subsequent sign-in each succeeded. Do not probe signup/resend with a real user's address.
- Keep the layers explicit: provider adapter tests, API-to-provider integration tests, mobile request/link parsing tests, safe deployed contract probes, then a dedicated inbox/device end-to-end run. The first layers must not send email; only the isolated end-to-end run may do so.
- Old links retain the redirect selected at their creation. After changing redirects, verify with a newly generated message and direct the user to resend rather than repeatedly retrying the stale URL.
