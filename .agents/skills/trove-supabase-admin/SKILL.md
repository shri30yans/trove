---
name: trove-supabase-admin
description: Administer the Trove Supabase project (auth config, email templates, user/session operations) through the Management API using the locally stored access token.
---

# Trove Supabase admin

Manage hosted Supabase configuration for the Trove project without the dashboard.

## Credentials

- Management API token: read it from `.secrets/supabase-access-token` at the repo root (gitignored; never print its value, never copy it into tracked files, command output, or commits). If the file is missing, ask the user to create a scoped personal access token at Dashboard → Account → Personal access tokens and store it there.
- Resend API key (unrestricted): `.secrets/resend-api-key`. Sending domain `mail.trove.zyphrlabs.com` (region ap-northeast-1, Resend domain id `4625db78-a2ff-4f44-8975-300000efc145`) is verified via Cloudflare DNS. Resend SMTP: host `smtp.resend.com`, port `465` (string in the API), **user `resend`** (not `resend_api_key` — that fails with a misleading `535 Invalid username`), password = the API key. Resend refuses `@example.com`/`@example.test` recipients with `550`, so SMTP probes need a real address; `smtp.resend.com` also accepts port 587 STARTTLS.
- Cloudflare API token (zone-scoped DNS edit for zyphrlabs.com): `.secrets/cloudflare-api-token`; use with `Authorization: Bearer` against `api.cloudflare.com` (the wrangler OAuth token lacks `dns_records` scope).
- Project ref: `enupfdacvbaugbotkrie` (also derivable from `SUPABASE_URL` in `config.toml`).
- The backend's `sb_secret_*` key in Heroku config does NOT work on GoTrue admin endpoints (they require a legacy service-role JWT); use the Management API instead.

## Calling the Management API

```sh
TOK=$(cat .secrets/supabase-access-token)
curl -s "https://api.supabase.com/v1/projects/enupfdacvbaugbotkrie/config/auth" \
  -H "Authorization: Bearer $TOK"
```

- `api.supabase.com` is reachable directly from this network. `*.supabase.co` is DNS-blocked here (see project memory); if it must be reached, add `--doh-url https://cloudflare-dns.com/dns-query` to curl.
- Config changes are `PATCH` to `/v1/projects/<ref>/config/auth` with JSON bodies; always read the endpoint back afterwards to confirm the change applied.
- Do not print a full auth-config response. It contains SMTP and template settings. Use a small script that prints only the exact allowlisted fields being inspected; never print Authorization headers, access tokens, SMTP passwords, or response bodies that may include them.

## Safe API release probes

The auth behavior also depends on the active Trove API release. Compare deployed code with the intended commit using `heroku releases --app trove --num 3`, then run `make auth-release-check` after deployment. The probe uses empty JSON bodies and never sends email.

**Never run `heroku releases:info`, `heroku config`, or `heroku config:get` in a response-visible terminal.** Heroku CLI release detail output can include all config vars, including database, storage, Supabase, and service-account credentials. If a command unexpectedly prints secrets, stop, do not quote or forward the values, and coordinate rotation of every exposed credential.

## Known constraints (verified 2026-10-09)

- Free tier + default email provider rejects ALL email-template edits and `smtp_sender_name`. Configuring custom SMTP unlocks them — DONE: Resend SMTP is now active on the project, sender name "Trove" and the confirmation/recovery templates are set. Keep `smtp_*` intact when patching other fields.
- `smtp_port` must be sent as a **string** in PATCH bodies; a number is rejected.
- **`smtp_pass` cannot be written through the Management API** (verified 2026-10-09): `PATCH /config/auth` answers `200` and silently discards it, alone or alongside `smtp_host`/`smtp_user`/`smtp_sender_name`, even though the OpenAPI `UpdateAuthConfigBody` lists the field. The spec offers only `patch`/`post` on that path — there is no PUT. Every other SMTP field, including `smtp_user`, does apply, and GET read-back is truthful, so a stale read-back means genuinely unchanged. Set the password in Dashboard → Authentication → SMTP settings and confirm by authenticating to `smtp.resend.com` from the backend's side, not by trusting the PATCH status code.
- Auth rate limits are per-minute: `rate_limit_email_sent` defaulted to `2`, which 429s sign-ups (GoTrue reports it as `500 unexpected_failure / "Error sending confirmation email"` or `429 over_email_send_rate_limit`, never as a credential error). Raised to `10` on 2026-10-09. `smtp_max_frequency = 60` is Supabase's separate legacy knob.
- Non-template auth settings (e.g. `site_url`) can be patched normally.

## Verification etiquette

Report exactly which fields were changed and show the read-back values. If a change is rejected by plan limits, state the blocker and the cheapest unblock (custom SMTP via a free transactional provider) instead of claiming completion.
