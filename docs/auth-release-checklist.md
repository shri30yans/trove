# Auth release checklist

Trove auth spans three independently changing parts: the Expo app, the Python API, and Supabase Auth configuration. A code check proves only the checked-out source. A successful health endpoint proves only that some API process is running.

## Test layers

| Layer | Test | What it proves | What it does not prove |
| --- | --- | --- | --- |
| Provider adapter | `tests/test_supabase_auth.py` | Supabase paths, payloads, redirects, and provider failure translation | Route wiring, deployed release, SMTP delivery |
| API-to-provider integration | `tests/test_auth_api_flow.py` | HTTP request → FastAPI route → Supabase adapter using an isolated provider transport | Real Supabase behavior or email delivery |
| Mobile contract | `mobile/tests/client.test.cjs` | API URL, request payload, response/session handling | Native router launch or real network |
| Link-state unit | `mobile/tests/auth-confirmation-link.test.cjs` | Success, token, malformed, and Supabase error callback classification | OS handoff from Mail/browser into the installed app |
| Production contract | `tools/check_auth_release.py` | Active API route registration and response types | A real account, SMTP, Supabase, or app launch |
| End to end | Dedicated synthetic inbox + simulator | Delivery, actual confirmation redirect, app handoff, and sign-in | Other users' mailbox/provider conditions |

The first five layers run without a user inbox. Keep the end-to-end test separate because it needs an isolated account and actual delivery. It should run for a release candidate against a dedicated synthetic inbox, never as a generic smoke test against a user's email.

## Before release

1. Run the applicable mobile and backend checks.
2. Confirm tests assert that signup and resend pass the HTTPS `/v1/auth/confirm-email` landing URL derived from `MCP_PUBLIC_URL`.
3. Confirm `mobile/app.json` declares the `trove` scheme and Supabase's redirect allow list contains both the HTTPS landing URL and `trove://confirm-email` for the app handoff.
4. Compare the intended source revision to the active Heroku release with `git rev-parse --short <ref>` and `heroku releases --app trove --num 3`.
5. Preserve user data and uncommitted work; deploy only the reviewed commit.

Never run `heroku releases:info`, `heroku config`, or `heroku config:get` in an output-visible session. Heroku CLI output can include production secret values.

## After API release

Run this safe contract probe:

```sh
make auth-release-check
```

For a stage API or another local target, call the script directly with its HTTPS origin (or an HTTP loopback URL).

It checks liveness, signup/resend/confirmation route registration using empty JSON bodies, the browser confirmation fallback page, and the email logo asset. It does not send email. Each auth route must return the API's structured `invalid_auth_request` response; a 404 or plain-text response means the deployed route table is stale or misconfigured.

## End-to-end confirmation

Use a dedicated synthetic account and inbox. Submit signup once, verify delivery, inspect that the generated confirmation URL redirects to the HTTPS Trove landing page, then test both the browser fallback and its `trove://confirm-email` app handoff on a device with the app installed. Confirm that the session is stored and sign-in completes. Test resend only from that account and check for provider throttling. Never submit a private user's address as a probe.

An email link contains a one-time token and captures its redirect when created. Once redirects are fixed, resend a fresh email; changing `site_url` later does not rewrite existing links.

## Supabase template update

- Preserve the current SMTP values when patching auth configuration.
- Include the hosted logo URL from the authenticated Trove API in email HTML.
- Keep Supabase's `{{ .ConfirmationURL }}` placeholder intact.
- Read back only the subject/content fields changed. Do not print the full Management API response or bearer token.
- Confirm the image endpoint and template after the API release; email clients may defer remote images until the recipient allows them.

## Report evidence separately

Record source revision and active release revision, local test results, safe live probe results, a synthetic email/device result, and any mobile simulator/release evidence. Never call the flow end-to-end verified based only on unit tests, an API health check, or the route probe.
