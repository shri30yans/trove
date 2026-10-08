# Mobile API contracts

`src/api/client.ts` owns authentication, bounded HTTP transport and HTTP error translation. Every JSON request requires a Zod response schema. Successful JSON is unknown until validation succeeds; there is no caller-selected cast to an arbitrary response type.

`src/api/schemas/` owns endpoint request and response projections, grouped by domain. Input schemas reject unknown writable fields. Response schemas validate required fields while stripping unknown extensions. API adapters validate identifiers, query filters and writable payloads before sending. A nullable field is distinct from an omitted field.

List cards, search hits, resurfacing summaries and full details have separate contracts. A card cannot acknowledge a capture. Upload transfer and completion validate their returned asset identity; transfer also validates received byte count. Capability flags are read-only preferences fields. Delivery requires an existing stable operation key, capture date and durable checkpoint callback.

`src/types.ts` re-exports schema-derived types. The Memory presentation model deliberately accepts different validated projections and local captures. It is not a wire-response schema.

Preferences use Query-owned request state. Loading and failed preferences do not become fabricated server settings. API configuration must be explicit; a missing address produces an error instead of selecting localhost.

## Verification

The contract suite covers every JSON response shape, missing fields, invalid ownership IDs, read-only preference flags and partial acknowledgements. A backend test runs its actual memory-card serialization through the mobile runtime schema. Other fixtures are synthetic examples checked against the current Python serializers; they do not prove a live service deployment matches the contract.

Calendar rendering stays with Trove's themed component. Selection, month cells and exclusive date bounds have a separate pure owner and behavior tests. A calendar dependency is not needed to preserve this UI.

## Remaining boundary work

Remote asset and preview fields now contain validated API-relative resource paths. Image/audio/video sources use shared bearer-authenticated source resolution; attachment downloads and spreadsheet loading use the media adapter. Binary attachment downloads verify MIME type and declared/downloaded byte counts. Provider-signed read and upload URLs are no longer emitted. Live provider and native authentication, playback, range and cancellation verification remain required. Markdown exports validate the Space identifier, HTTP 200 status, ZIP content type, declared and downloaded byte counts, and the ZIP opening signature before returning a file to the share flow. Failed or malformed downloads are removed; a 401 retries once with renewed authorization. The schema work does not establish native runtime behavior.

Local preferences and search history now use a validated SQLite key-value store with explicit legacy migration and one shared lifecycle hook. Workspace overview reads now use TanStack Query for loading, refresh and visible errors. Confirmed Space creations survive older list responses; deleted memories remain hidden from resurfacing. Memory initial loading, refresh and pagination use one infinite Query. The library projection reconciles confirmed writes against request-start revisions: stale reads cannot overwrite newer edits, acknowledgements remain visible, deleted items cannot return, and later processing updates retain local-to-remote route identity. WorkspaceProvider composes these owners instead of maintaining request IDs and copied server lists.

Memory detail and related reads use separate ID-keyed queries with cancellation. Navigation selects an ID instead of issuing duplicate requests. Failed detail reads cannot promote partial list cards into editable detail records. Confirmed edits cancel stale reads before updating the detail cache and library; deletion cancels and removes the matching detail queries. Pending captures remain device-local until acknowledged. Space creation uses mutation-owned pending/error state and keeps its draft on failure.

The backend now provides authenticated `GET /v1/assets/{id}/content` and `GET /v1/memories/{id}/preview`. Database ownership and a non-deleted memory attachment are required before provider access. Responses stream private bytes with single-range support, declared lengths, and resource cleanup. These endpoints and mobile adapters are unit-tested; serializers and mobile sources use them. Real provider/native verification remains outstanding.

Live verification on 2026-10-07: the listening local API at port 4000 still emitted the old provider-URL allocation contract. Current handlers were then exercised via ASGI against the configured live database/storage with isolated synthetic identities and 41 bytes of synthetic content. Allocation passed the current mobile schema. Transfer failed at the S3 TLS boundary with SSL UNEXPECTED_EOF_WHILE_READING; the API returned 502 storage_unavailable. No persistence, acknowledgement, idempotent retry, range playback or ownership claim is established by this run. Resolve the configured storage connection and restart the running API before repeating the full path. Maestro now runs with the verified Temurin 17 runtime. Native verification is blocked by missing CocoaPods and a simulator whose iOS 27 runtime path is unavailable.

Signed-URL-specific public endpoint and expiry configuration have been removed. Upload allocation no longer advertises an expiry for its authenticated API path. An enabled semantic search reports embeddings_unavailable when inference fails; disabling embeddings deliberately selects lexical retrieval.

Space detail reads now use a focused infinite Query instead of duplicate initial/refresh requests and manual cursor flags. Move destinations use the shared themed ActionSheet. Moving a memory uses POST /v1/memories/{id}/move with required distinct fromSpaceId/toSpaceId fields. The server locks the owned memory, checks both active owned Spaces in the transaction, removes only the source membership and inserts the destination. Repeating an already-confirmed move is idempotent; unrelated memberships remain intact. Each confirmed item updates the library and disappears from the source immediately; failed items remain selected for retry.

Live database verification on 2026-10-07 passed for synthetic atomic move, retained membership, repeated operation, foreign-owner rejection, invalid same-Space request and validation by the current mobile detail schema. Synthetic memory and Spaces were deleted through API handlers. This was current-code ASGI against real persistence, not native UI or the stale listening service on port 4000. Six focused backend move regression tests also pass.

Binary HTTP contracts now have one owner in api/schemas/binary.ts: complete status, case-insensitive headers, normalized MIME and an exact positive byte count. Both exports and attachment downloads use api/download.ts for authenticated native transfer, one session renewal and partial-file cleanup. Network interruption removes the partial destination; cleanup failures are logged without replacing the original error. Exports separately validate their ZIP prefix. Spreadsheet reads validate the same full-response contract and reject 206 partial data.

Batch move coordination now lives under features/spaces, with mutation-owned busy state. Every confirmed item reconciles immediately. Later failures retain only their failed IDs for retry; presentation observer failure is reported as a refresh requirement and cannot reclassify a confirmed server move as failed.

Final-flow audit additions: stored-preference updates now derive synchronously from the validated SQLite value, so same-render history submissions cannot erase each other; unmigrated legacy history is kept rather than overwritten. Calendar month-grid alignment normalizes to day one while retaining the themed renderer. Negative related feedback uses a focused mutation, visible memory-specific error state and cancellation before cache reconciliation. Audio presentation has a separate owner with shared accessible controls; authenticated source/loading errors are visible for audio/video. Native playback remains unverified.

Native prerequisite audit on 2026-10-07: existing Maestro 2.11.0 runs with a temporary SHA-256-verified Temurin Java 17 runtime. The release gate now reaches pod --version and fails because CocoaPods is unavailable. Direct boot of the dedicated Trove Verification simulator also fails with CoreSimulator code 401: iOS 27 runtime path not found. A simulator inventory alone does not prove it can boot.


## Current verification matrix (2026-10-07)

| Requirement | Evidence | Remaining gate |
| --- | --- | --- |
| JSON contracts and request validation | Mobile typecheck/lint, 137 tests | Deploy matching API contract |
| Upload completion identity and size | First/repeated backend acknowledgement tests; mobile rejects missing/mismatched size before checkpoint | Live provider transfer, completion and safe retry |
| Durable local capture and acknowledgement ordering | SQLite restart/checkpoint/concurrency tests | Native transfer and restart exercise |
| Atomic Space moves | Synthetic live database test including retries and ownership rejection | Native interaction review |
| Shared keyboard/layout ownership | Static invariants and shared frame implementation | CocoaPods installation, working iOS runtime, screenshot review |
| Authenticated media | Backend ownership/range tests and mobile binary contract tests | Resolve storage TLS failure, verify playback on device |

The local API on port 4000 was observed serving the old allocation contract. The live storage probe failed with SSL UNEXPECTED_EOF_WHILE_READING (502 storage_unavailable). These are unresolved delivery gates; successful static checks do not supersede them.


Code-only follow-up: upload allocation, transfer and completion now live in `app/routes/uploads.py`, with typed database records and Pydantic response models. Both transfer and completion translate expected provider/connection failures at the same boundary; unexpected programming errors propagate. Local `app.run` uses Uvicorn reload for application changes. Ruff, formatting and mypy were checked; test execution and runtime verification were deferred at the user's request. Earlier test totals do not validate these follow-up changes. Existing processes must restart once to adopt the updated launcher. Earlier test totals do not validate these follow-up changes. Existing processes must restart once to adopt the updated launcher.


2026-10-07 UI/performance follow-up: Space creation now sends its optional description through the existing backend field. Search caches exact query/filter combinations for 30 seconds and keeps prior results labelled as updating during a request; confirmed memory mutations invalidate search data and deletion removes its cache. Backend search builds highlighted excerpts only after ranking and limiting matches. The API session owner retains the current token in memory, deduplicates concurrent token acquisition/renewal, and clears persisted stale tokens before renewal. Space creation logs insert duration without content. Static checks were run; user-requested test deferral remains in effect. No measured device or live latency improvement is claimed.

Cloud screen: `GET /v1/processing` returns whole-library server-side processing counts (queued, processing, ready, failed, total) because a paginated Memory list cannot answer this. The response validates through `processingSummarySchema`; the Cloud screen derives its Processed state from one pure owner (`processingView`) and shows embedding availability from the authoritative preference state. Capability flags remain read-only; the screen offers no processing switches. Native rendering is unverified without a simulator.
