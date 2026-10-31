> **Work in progress.** This is an early snapshot of a private personal memory app, published for reference rather than as a finished product. Expect rough edges, incomplete sections and breaking changes. No production credentials are committed here, but `config.toml` does carry the public production endpoints the app talks to.

# Trove

Trove is a private personal memory app with an Expo client and a Python backend. Supabase provides the hosted Postgres database, the vector extension, the Auth token issuer, and private file storage. One process serves the HTTP API and polls the database-backed memory queue. It sends text and image embedding requests to Gemini Embedding 2 through Vertex AI's native `embedContent` API; there is no generative AI enrichment, local model download, separate worker, or Redis.

`app/` is that backend: FastAPI for the HTTP surface, asyncpg for the one shared Postgres pool, and a server-only Gemini adapter for `gemini-embedding-2`. Text and images use the same 768-dimensional vector space. The queue loop runs in the same event loop as the request handlers. It also exposes a Streamable HTTP MCP endpoint for OAuth-linked note and Space tools; see [docs/mcp.md](docs/mcp.md) for its contract and current setup requirements.

`app/` is the Python backend. `mobile/` is the Expo client and has its own dependencies and build configuration.

## Environments

Select the environment explicitly with `RUN_ENV=local`, `RUN_ENV=stage`, or `RUN_ENV=prod`. Shared non-secret defaults and production public endpoints live in [`config.toml`](config.toml). The backend then loads the matching `local.env`, `stage.env`, or `prod.env` file from the working directory; process environment and Heroku Config Vars take precedence over both. Heroku's generated `PORT` takes precedence over `API_PORT`. `Procfile` selects `prod` for each Heroku process. Keep passwords, access/secret keys, service-account credentials, and the Supabase secret key in environment variables or Heroku Config Vars. Outside `RUN_ENV=local`, startup requires valid Auth endpoints, Supabase credentials, Vertex credentials, database TLS, a specific CORS origin, nonempty proxy configuration, and HTTPS Storage and MCP endpoints.

Copy `local.env.example` to `local.env`, then fill in a dedicated development Supabase project connection, Auth publishable (or legacy anon) key, Storage S3 credentials, and optional Vertex service-account credentials if you want embeddings locally. Provider credentials stay on the Trove backend and are never added to the mobile app. Use separate Supabase projects for local development, staging, and production. Do not point `local` or `stage` at production. Do not commit `local.env`, `stage.env`, or `prod.env`. Supabase Connect provides the Session pooler URL; use TLS (`sslmode=require`). In Supabase Storage, create the S3 access keys. Migration 003 creates the private `trove-private` bucket.

Use the Supabase **Session** pooler, not the Transaction pooler: the vector search queries issue `SET LOCAL hnsw.*`, which needs session semantics.

## Local development

Prerequisites: Python 3.12 or newer. Docker is no longer needed.

```sh
cp local.env.example local.env
# Fill in the Supabase session-pooler URL, Storage S3 keys, and project region.
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
RUN_ENV=local python -m app.migrate
RUN_ENV=local python -m app.run
```

There is no local Postgres, RustFS, or embedding container; Supabase hosts Postgres and storage, and embeddings are generated through Vertex AI's native `embedContent` API. Set the base64-encoded service-account JSON (`VERTEX_SERVICE_ACCOUNT_JSON_B64`) in `local.env` to enable them; `config.toml` names the Vertex project. The API listens at `http://localhost:4000`. The Expo app can use `http://localhost:4000` on iOS Simulator or `http://10.0.2.2:4000` on the standard Android emulator.

Embedding requests are sent only by the backend to Vertex AI using OAuth service-account credentials, `VERTEX_PROJECT_ID`, and `VERTEX_LOCATION`; these credentials and memory content never go to the mobile client. Trove does not call a summarization, transcription, or answer-generation model. The API does not download or load model weights. If the embedding configuration is missing locally, embedding jobs remain queued and `GET /health/embeddings` reports the missing configuration; semantic search reports an explicit unavailable error when enabled. Keyword search remains available when embeddings are disabled for an account.

Email/password sign-in, session refresh, and sign-out are proxied through the Trove API. Provider access tokens are verified against the configured JWKS URL and issuer in every environment. The app has no local sign-in bypass or account-creation flow. For device testing, provision a synthetic user in a dedicated development Supabase Auth project and sign in through the same app screen. `AUTH_JWKS_URL`, `AUTH_ISSUER`, and `SUPABASE_URL` come from `config.toml` for the project it describes, so a different Supabase project overrides them; `SUPABASE_AUTH_API_KEY` stays per-environment because the file does not carry a project value. It is that project's publishable key (or legacy anon key), which Supabase designs to be public and ships inside client bundles, and it is the one Auth key that is not a credential: startup refuses a secret or service-role key in that field.

```sh
curl -s localhost:4000/health/live
curl -s localhost:4000/health/embeddings
```

## Heroku deployment

The root `Procfile` defines a `release` migration phase and one `web` process. Set the app to the Heroku Python buildpack (`heroku buildpacks:set heroku/python`); `.python-version` pins 3.12. Configure Heroku Config Vars from `prod.env.example`. `config.toml` supplies the production endpoints, the Vertex project, and every other non-credential setting; set the database URL, Storage access/secret keys, the Supabase Auth publishable and secret keys, and the Vertex service-account JSON. `python -m app.config` prints the effective configuration with every credential masked, and every `config.toml` profile is validated at every startup, including the one this process is not booting. Do not set `API_PORT` or Heroku's generated `PORT`; the app binds the port Heroku assigns. Never put provider/database credentials in the client app. OAuth-based MCP linking also requires enabling and configuring the Supabase OAuth Server; see [docs/mcp.md](docs/mcp.md).

Heroku's common runtime publishes no router address ranges and documents `X-Forwarded-For` as untrusted, so `PROXY_TRUSTED_IPS` stays `*` in production: the address bucket is only used for anonymous traffic, and authenticated requests are limited by a digest of their own bearer token instead. See `Request handling notes` below.

Account deletion is available in Profile. `DELETE /v1/auth/account` schedules deletion seven days later. During that recovery window, the account is locked to a screen where the owner can cancel deletion and keep their memories. After the deadline, a backend worker removes private objects under the user's UUID prefix, cascades the user's Trove database rows, and deletes the Supabase Auth user through the server-only secret key. When the app next confirms deletion, it clears local pending captures and account preferences before allowing another sign-in. A small tombstone containing only the Auth subject is retained to reject access tokens that remain valid until expiry; it also makes deletion safe to retry after a provider outage. Configure `SUPABASE_SECRET_KEY` in each non-local environment. Users may create a new account afterward; it receives a new Auth subject and starts empty. Deletion email notifications require a separately configured transactional email provider; no email provider is configured in this repository yet.

The web process runs two fixed queue consumers against one shared database pool, which is hard-capped at five connections per dyno for both API requests and workers. Keep the Heroku web process at one dyno unless the Supabase pooler budget is recalculated; each additional dyno has its own five-connection cap. The shared processing queue selects ready paid-plan jobs before free-plan jobs, with FIFO order within each plan.

Inbound file transfers also pass through one bounded admission queue shared by all users on the web process: at most two transfers run at once, up to eight wait, and paid-plan transfers are selected first with FIFO order within each plan. This limits temporary disk and storage pressure without holding database connections while files are queued or transferred. A full wait queue returns a retryable response; the mobile outbox keeps the capture and retries it. Keep one web dyno for this priority order to cover every user globally. Upload bodies bypass the small JSON request-body buffer and are streamed to temporary files under the configured per-file byte limit.

A failed `release` migration prints `Database migration failed: ...` and exits 1, which blocks the deploy. If the web process cannot reach Postgres or Storage, it logs `Could not start Trove API: ...` and exits instead of serving a half-initialized API.

`tests/test_asgi_smoke.py` is the offline route-table and ASGI check: it asserts the published surface, that every protected operation answers `401` to an anonymous caller, and that unknown paths, `/docs`, `/openapi.json`, and a removed local sign-in route stay unavailable. It needs no database, bucket, or provider and runs with `make check` / `pytest`.

### Embedding API and reindexing

Gemini Embedding 2 returns 768-dimensional vectors for text and images. Migration `20261008175011_switch_to_gemini_embedding_2.sql` clears incompatible derived vectors, updates the pgvector width, and queues eligible saved memories for re-embedding. Reindexing sends existing memory text and image bytes to Vertex AI and incurs provider usage charges; review Vertex AI pricing before applying it to a database with existing memories. Configure base64-encoded service-account JSON (`VERTEX_SERVICE_ACCOUNT_JSON_B64`) in the backend and restart it; `config.toml` already names `VERTEX_PROJECT_ID` and `VERTEX_LOCATION` for this project. `/health/embeddings` reports whether provider credentials are configured; it does not call Vertex AI as a health probe.

Run `RUN_ENV=local .venv/bin/python -m app.embedding_check` to make one live Vertex AI request with a fixed synthetic text and verify the response dimensions and norm. It prints no credentials, input, or vector. The command exits with code 2 when provider configuration is missing and code 1 when the request fails.

### Request handling notes

- The API rejects request bodies over 1 MB with `413 payload_too_large`, including chunked bodies; file bytes use the authenticated upload-content endpoint with the configured upload limit. Downloads and media playback also use authenticated API endpoints; provider URLs and credentials stay server-side.
- Requests are rate limited to 240 per minute per client in a sliding window that lives in this process, so the ceiling scales with dyno count; the deployed web process is one dyno. Authenticated traffic is bucketed by a digest of its bearer token, never the token itself, so an untrustworthy forwarded address cannot buy extra budget for a signed-in caller; anonymous traffic is bucketed by address. Uvicorn trusts `X-Forwarded-For` only from `PROXY_TRUSTED_IPS`, which is `*` in production because Heroku's common runtime publishes no router ranges -- that is why the limiter does not depend on the address for authenticated traffic.
- `GET /v1/explore` now returns `months[].month` as a plain `YYYY-MM-DD` date rather than a full UTC timestamp; `new Date(...)` parses both identically.

## React Native app

```sh
cd mobile
cp .env.example .env
npm install
npx expo prebuild
npm run ios
```

The share receiver supports text, webpages, images, video, audio, and files in a custom development client. Mobile email/password sign-in uses the Trove API, which proxies Supabase Auth; provider keys stay server-side.

## Website

The same Expo Router client can also run as a website; the directory name does not restrict its platforms. Run `cd mobile && npm run web` for local development, or `cd mobile && npx expo export --platform web` to produce a static website bundle in `mobile/dist`. Production Expo builds use `https://api.trove.zyphrlabs.com` from `mobile/.env.production`.

## API surface

- `POST /v1/memories`, `GET /v1/memories`, and `GET /v1/memories/:id` capture and browse memories.
- `POST /v1/uploads` and `POST /v1/uploads/:id/complete` create private file uploads.
- `GET /v1/search` combines keyword search with shared-space text-to-image similarity when embedding search is enabled.
- `GET /v1/memories/:id/related` finds related text and visually similar image memories.
- `/v1/spaces`, `/v1/preferences`, `/v1/explore`, and `/v1/updates` manage Spaces and optional embedding-based resurfacing.
- `/health/live`, `/health/ready`, and `/health/embeddings` are unauthenticated; `/health/embeddings` is new with the in-process runtime.

See [TROVE_PRODUCT_PLAN.md](TROVE_PRODUCT_PLAN.md) for product scope and `design-reference/` for the visual design source.
