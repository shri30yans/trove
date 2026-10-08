# Library decisions

Adopted: react-native-keyboard-controller owns keyboard layout, with Expo-compatible Reanimated and Worklets. Sources: https://docs.expo.dev/versions/v57.0.0/sdk/keyboard-controller/ and https://kirillzyusko.github.io/react-native-keyboard-controller/docs/api/components/keyboard-avoiding-view.

Adopted: TanStack Query owns Search request identity, cancellation, data and errors; use-debounce owns timing. Filters belong in the query key. Read failures surface without automatic retries or focus/reconnect refetch. Explicit invalidation follows mutations.

## Durable delivery

Implemented: Expo SQLite for a transactional outbox instead of rewriting one AsyncStorage JSON array and serializing writes with a promise tail. Persist captures, retry times and upload checkpoints. A focused worker still owns the Trove upload/acknowledgement protocol. Existing AsyncStorage data migrates transactionally and remains intact on failure. Define account/backend ownership before account switching.

Persisted TanStack mutations do not replace durable attachment storage or atomic acknowledgement. Preserve stable idempotency keys and commit acknowledgement before cleanup. Keep restart, concurrency, checkpoint and acknowledgement tests throughout migration. Acknowledged records remain until attachment cleanup completes; cleanup resumes on foreground entry without another upload. Zod validates the persisted domain records.

## Other candidates

- Keep the themed calendar: pure date-selection/grid/bounds helpers, localized labels, and accessibility states preserve the existing interaction without another UI owner.
- Zod now validates all mobile JSON API request/response contracts, persisted captures, local preferences and binary response metadata. Schema types replace handwritten wire DTOs.
- Query owns workspace, library pagination, Space lists, detail/related reads, Search and server preferences. Focused reconciliation preserves acknowledged captures and confirmed mutations.
- Keep simple theme tokens and UI primitives local. A UI framework adds another design owner without simplifying the domain flow.


## Next improvements, in priority order

1. Restore native and provider verification before expanding the architecture: the current evidence cannot establish keyboard clearance or live media delivery.
2. Add contract compatibility checks to CI. Mobile Zod schemas validate runtime payloads today; backend explicit response models and generated OpenAPI types are a candidate for reducing duplicated wire definitions. Generation must cover endpoint projections and refinements, rather than replacing runtime validation with TypeScript assertions.
3. Separate upload handling from memory CRUD in `app/routes/memories.py` when extending either flow. Keep ownership checks explicit and extract only genuinely shared domain operations; a service class for every endpoint would add indirection.
4. Keep shared UI tokens and semantics under one owner. Extend existing fields, buttons, notices, frames and sheets for real repeated behavior; do not add a second UI kit.

Do not replace the capture outbox with a generic retry library or persisted Query mutations: those do not own attachment durability, transactional acknowledgement, or cleanup. Adopt another library only for a concrete repeated mechanism with a supported Expo version and a measurable reduction in maintained code.
