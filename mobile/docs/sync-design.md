# Durable save delivery

A local save, an API acknowledgement, and downstream processing are separate milestones. Connectivity only permits an attempt. All remote operations use the authenticated Trove API.

## Ownership

| Owner | Responsibility |
| --- | --- |
| domain/pending-capture.ts | Zod validation, required capture dates and retry metadata |
| storage/capture-outbox.ts | SQLite records, atomic migration, checkpoints, acknowledgements and committed snapshots |
| features/sync/capture-files.ts | Preserve temporary attachments and remove app-owned copies |
| features/sync/save-capture.ts | Validate, copy, commit, then report a local save |
| features/sync/deliver-captures.ts | One API delivery worker, stable keys, upload checkpoints, retry classification and acknowledged cleanup |
| features/sync/use-capture-delivery.ts | Queue/worker states, connection and foreground subscriptions, one due-time scheduler |
| WorkspaceProvider | Route the chosen Space and reconcile acknowledged memories into the library |

SQLite uses WAL and FULL synchronization. Record updates are synchronous and short; no network or filesystem operation runs inside a transaction. SQL uniqueness protects operation and local IDs. There is no custom write promise chain and no whole-queue replacement.

## Migration

On first open, validate the legacy AsyncStorage queue and preserve its operation keys, files, upload IDs, attempts, retry times and capture dates. Import all rows and the migration marker in one SQLite transaction. A validation or constraint failure rolls back the import and leaves the legacy data intact. Remove legacy storage only after commit. The marker prevents resurrection even if legacy removal fails or execution stops before it finishes.

## Save and delivery

1. Validate the capture and copy attachments into document storage.
2. Commit a pending record with a timestamp and cryptographic UUID identity. Only then report a local save.
3. When settings are loaded, automatic sync is enabled, the app is active and connectivity permits it, schedule the earliest eligible retry. No polling.
4. Process oldest-first. Reuse completed file IDs and commit each upload checkpoint before creating the memory.
5. Submit with the same idempotency key on every retry. The API owns authentication, ownership, storage and server persistence.
6. Mark the record acknowledged in SQLite before releasing its local files. Reconcile each acknowledged memory immediately, including a partial batch.
7. Delete the attachment copies, then remove the acknowledged cleanup record. Failed cleanup remains durable and runs on the next foreground entry or sync without resubmitting the memory.

A failed acknowledgement write retains the pending record and files for an idempotent retry. Observer failures do not reverse durable saves. A stale remote page cannot erase newly acknowledged memories.

## Retry and status

Transient transport errors, timeouts, 408, 429 and server errors use bounded exponential backoff with jitter. Other 4xx errors and missing local files require attention; automatic delivery excludes them. Manual sync retries blocked/delayed records once. Changing the automatic-sync preference or leaving the foreground stops the next item, while an already-started item may finish.

The hook represents queue initialization and worker activity explicitly. Status derives from those states and the committed records. Corrupt storage surfaces an error; it is never silently replaced with an empty queue. Server-side processing failure does not mean the local save is still undelivered.

## Limits and verification

This is a foreground outbox for the existing single-account/backend client. Before introducing login switching, scope records and cached credentials to their authenticated owner and API. OS background delivery and a permanent offline replica need separate policies and native verification.

Tests execute the production TypeScript against real SQLite through a Node adapter, including closing/reopening a file database. Native filesystem, network and API adapters are mocked in these tests. Coverage includes migration rollback, stale legacy data, concurrency, restart recovery, checkpoints, permanent rejection, acknowledgement failures and cleanup recovery. These tests do not prove native suspension, picker, transfer or keyboard behavior.

Run `npm run check` and the native gate in `docs/ui-verification.md` before release. New native dependencies require rebuilding the development client. Expo SQLite web support requires WASM and cross-origin isolation; Metro supplies these for preview. Deployed web hosting must also send COEP `credentialless` and COOP `same-origin` headers.
