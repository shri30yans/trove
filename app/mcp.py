"""Trove's OAuth-protected MCP application entry point.

The API process mounts this ASGI app and owns its shared database, queue, and
embedding lifecycle. Tool behavior and token verification live in focused modules.
"""

from __future__ import annotations

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from app.config import get_config
from app.mcp_auth import SupabaseTokenVerifier
from app.mcp_tools import register_tools

config = get_config()
if not config.AUTH_ISSUER:
    raise RuntimeError("AUTH_ISSUER is required for MCP OAuth discovery")

resource_url = AnyHttpUrl(config.MCP_PUBLIC_URL)
server = FastMCP(
    "Trove",
    instructions=(
        "Search and organize the authenticated user's Trove notes. Search uses Trove's hybrid text and "
        "embedding search when enabled. Only update Space descriptions when the user asks. Never infer a "
        "different user's identity or access notes outside the authenticated account."
    ),
    stateless_http=True,
    streamable_http_path="/mcp",
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(config.AUTH_ISSUER.rstrip("/")),
        resource_server_url=resource_url,
        validate_token_resource=True,
    ),
    token_verifier=SupabaseTokenVerifier(),
)
register_tools(server)
app: Starlette = server.streamable_http_app()
