# HTTP API

All application endpoints are under `/v1`. Send JSON with `Content-Type: application/json`; authenticated routes require `Authorization: Bearer <access-token>`. Errors use `{ "error": { "code": "...", "message": "..." } }`.

The OAuth-protected Streamable HTTP MCP endpoint is `/mcp`; see [Trove MCP](mcp.md) for its tool contract and deployment prerequisites.

## Search and memory listing

Search uses one set of filters whether or not a text query is present. `after` is inclusive and `before` is exclusive for both endpoints. Dates are ISO 8601 timestamps.

```http
GET /v1/search?q=orange%20button&kind=image&after=2026-01-01T00%3A00%3A00Z&before=2026-02-01T00%3A00%3A00Z&limit=30
Authorization: Bearer <access-token>
```

```json
{
  "query": "orange button",
  "semanticSearch": true,
  "memories": [{ "id": "…", "kind": "image", "capturedAt": "2026-01-14T…Z", "matchType": "meaning" }]
}
```

For browsing without a text query, use the same filters on the paginated memory list:

```http
GET /v1/memories?kind=image&after=2026-01-01T00%3A00%3A00Z&before=2026-02-01T00%3A00%3A00Z&limit=50
Authorization: Bearer <access-token>
```

The list response is `{ "memories": [...], "nextCursor": "..." }`; pass `nextCursor` as `cursor` to fetch the next page. Both endpoints also accept `spaceId` and `source`. Search additionally accepts `q` (required, up to 1,000 characters); `kind` accepts `text`, `link`, `image`, `video`, `audio`, or `file`. Limits are bounded by the server.

## Endpoint index

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/v1/me` | Current authenticated user |
| `GET`, `POST` | `/v1/spaces` | List or create Spaces |
| `PATCH`, `DELETE` | `/v1/spaces/{spaceId}` | Update or delete a Space |
| `GET`, `POST` | `/v1/memories` | List memories or create one |
| `GET`, `PATCH`, `DELETE` | `/v1/memories/{memoryId}` | Read, update, or delete a memory |
| `POST` | `/v1/memories/{memoryId}/restore` | Restore a deleted memory |
| `POST` | `/v1/memories/{memoryId}/retry` | Retry memory processing |
| `POST` | `/v1/uploads` | Create a direct-upload request for an asset |
| `POST` | `/v1/uploads/{assetId}/complete` | Verify and complete an asset upload |
| `GET` | `/v1/search` | Search memories by text, type, source, Space, and capture date |
| `GET` | `/v1/memories/{memoryId}/related` | Find related memories |
| `PUT` | `/v1/memories/{memoryId}/related/{relatedId}/feedback` | Save related-memory feedback |
| `GET`, `PATCH` | `/v1/preferences` | Read or update account preferences |
| `GET` | `/v1/export/markdown` | Download a Markdown ZIP of the library or one Space, including original attachments |
| `GET` | `/v1/explore` | List monthly memory counts |
| `GET` | `/v1/updates` | Fetch resurfacing updates |

Health checks are unauthenticated at `/health/live`, `/health/ready`, and `/health/embeddings`. Interactive OpenAPI routes are disabled in the application, so this file is the human-readable endpoint reference.

## Markdown export

```http
GET /v1/export/markdown?spaceId=<space-id>
Authorization: Bearer <access-token>
```

Omit `spaceId` to export the full library. The endpoint returns `application/zip` with Markdown memory files, Space indexes, and original attachments from private Storage. A Space export contains that Space's memories only.
