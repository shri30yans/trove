# Trove MCP

The backend exposes a stateless Streamable HTTP MCP endpoint at `/mcp`. It uses the configured Supabase Auth OAuth issuer to discover and validate linked-user access tokens. The MCP delegates to the existing Trove API behavior, so search, pagination, Space ownership, and note ownership keep the same contract. Its adapters are in `app/mcp_tools.py`, token identity checks are in `app/mcp_auth.py`, and `app/mcp.py` is the ASGI entry point mounted by the API process.

## Tools

| Tool | Behavior |
| --- | --- |
| `list_spaces` | Lists the caller's Spaces, descriptions, and note counts. |
| `list_notes` | Lists recent notes, optionally filtered by `space_id` or `kind`, with cursor pagination. |
| `search_notes` | Uses Trove hybrid text and embedding search, optionally filtered by `space_id`. |
| `get_note` | Gets a note owned by the caller. Large content fields are capped at 12,000 characters and marked as truncated. Attachment URLs are omitted. |
| `update_space_description` | Sets or clears one of the caller's Space descriptions. |
| `disconnect_trove` | Revokes the current OAuth client's Trove grant and sessions when the user asks to disconnect. |

List and search return compact note summaries. Search only uses semantic matching when the user's Trove embedding preference and server configuration allow it; the underlying API reports embedding outages as errors. `disconnect_trove` revokes the Supabase Auth grant for the connected OAuth client, invalidating that client's Trove sessions. Trove tool access is granted as one fixed tool set after explicit approval; the OIDC profile scopes shown by Supabase do not act as per-tool permissions.

OAuth-issued Supabase JWTs carry a `client_id` claim. Trove's ordinary REST API rejects those tokens, limiting linked clients to the MCP tools advertised here. The MCP validates the JWT issuer, MCP-specific audience, signature, expiry, live Supabase session, account-deletion state, and user ownership. It checks the live session with Supabase Auth on each MCP request so `disconnect_trove` takes effect for subsequent calls. `get_note` is a side-effect-free read and does not add an in-app “opened” event.

## Configuration

Set `MCP_PUBLIC_URL` to the externally reachable HTTPS MCP URL in each deployed environment, including `/mcp`. This URL is required by OAuth protected-resource discovery. Local development defaults to `http://localhost:4000/mcp`.

The Supabase project must have its OAuth 2.1 server enabled, with dynamic client registration enabled for MCP clients. Set its issuer to the existing `AUTH_ISSUER`, its Site URL to the API host, and its authorization path to `/oauth/consent`. The backend serves that path: the current sign-in page uses Trove's email-and-password sign-in, then displays the requesting client and scopes for explicit approval. Supabase Auth issues and refreshes OAuth tokens. If the Supabase project enables additional sign-in methods, add matching flows to this hosted page before offering those methods for MCP account linking.

Configure a Supabase Custom Access Token Hook so OAuth-issued tokens have the MCP resource URL as their `aud` claim. The verifier rejects OAuth tokens without this audience; ordinary Trove account tokens keep the existing `authenticated` audience. Example hook response logic:

```ts
const { claims } = await req.json()
const customClaims: Record<string, unknown> = {}
if (typeof claims.client_id === "string") {
  customClaims.aud = Deno.env.get("TROVE_MCP_PUBLIC_URL")
}
return new Response(JSON.stringify({ claims: customClaims }), {
  headers: { "Content-Type": "application/json" },
})
```

Set the hook's `TROVE_MCP_PUBLIC_URL` value to the exact `MCP_PUBLIC_URL`, including `/mcp`. The protected-resource discovery document is at `/.well-known/oauth-protected-resource/mcp`.

These project settings and the token hook are external to this repository and still need to be enabled in Supabase for each environment. Until then, MCP requests fail closed because tokens lack the MCP audience. Keep the endpoint private until OAuth Server, dynamic registration, the token hook, and the full authorization redirect have been verified.

After setup, ChatGPT can connect to `MCP_PUBLIC_URL` using OAuth, subject to the user's ChatGPT account and workspace feature availability. `.mcp.json` remains the development-only Supabase management connection; it is not the Trove MCP endpoint.
