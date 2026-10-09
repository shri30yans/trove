"""MCP tool contracts and adapters to Trove's existing API behavior."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Annotated, Any, TypeVar

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from app import supabase_auth
from app.errors import ApiError, dump_json
from app.mcp_auth import current_principal, current_subject, oauth_client_id
from app.memory_reads import get_memory_detail, list_memories_for_user
from app.routes import search, spaces
from app.schemas import UpdateSpaceRequest

_Result = TypeVar("_Result")


async def _trove_result(operation: Awaitable[_Result]) -> _Result:
    """Translate a Trove API error into a concise MCP tool error."""
    try:
        return await operation
    except ApiError as error:
        raise ValueError(error.message) from error


def _serialize_tool_result(payload: object) -> dict[str, Any]:
    """Apply Trove's ISO timestamp and UUID wire encoding to MCP structured results.

    Every result crosses through the API's own encoder, so a tool cannot present a Memory differently
    from the route that serves it. Trimming happens after this step because the models are immutable.
    """
    return json.loads(dump_json(payload))


def _note_summary(note: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "kind",
        "status",
        "sourceApp",
        "sourceDomain",
        "title",
        "description",
        "userNote",
        "capturedAt",
        "spaces",
        "matchType",
        "matchExcerpt",
        "score",
    )
    return {field: note[field] for field in fields if field in note}


def register_tools(server: FastMCP) -> None:
    """Register the Trove note and Space tools on the MCP server."""

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    async def list_spaces() -> dict[str, Any]:
        """List the signed-in user's Spaces, descriptions, and note counts."""
        subject = await current_subject()
        payload = await _trove_result(spaces.list_spaces_for_user(subject))
        return _serialize_tool_result(payload)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    async def list_notes(
        space_id: str | None = None,
        kind: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List recent notes, optionally filtered to a Space or note type. Use nextCursor to fetch another page."""
        values = {"limit": str(limit)}
        if space_id:
            values["spaceId"] = space_id
        if kind:
            values["kind"] = kind
        if cursor:
            values["cursor"] = cursor
        principal = await current_principal()
        payload = _serialize_tool_result(await _trove_result(list_memories_for_user(principal, values)))
        payload["memories"] = [_note_summary(note) for note in payload["memories"]]
        return payload

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    async def search_notes(
        query: Annotated[str, Field(min_length=1, max_length=1000)],
        space_id: str | None = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> dict[str, Any]:
        """Search notes by meaning or words using Trove's hybrid search; optionally limit results to a Space."""
        values = {"q": query, "limit": str(limit)}
        if space_id:
            values["spaceId"] = space_id
        principal = await current_principal()
        payload = _serialize_tool_result(await _trove_result(search.search_memories_for_user(principal, values)))
        payload["memories"] = [_note_summary(note) for note in payload["memories"]]
        return payload

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
    async def get_note(note_id: str) -> dict[str, Any]:
        """Fetch one note without recording an in-app open event."""
        principal = await current_principal()
        detail = await _trove_result(get_memory_detail(note_id, principal))
        payload = _serialize_tool_result({"memory": detail})
        note = payload["memory"]
        content_limit = 12_000
        for field in ("contentText", "pageText"):
            value = note[field]
            if isinstance(value, str) and len(value) > content_limit:
                note[field] = value[:content_limit]
                note[f"{field}Truncated"] = True
        for asset in note["assets"]:
            asset.pop("url")
        return payload

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    )
    async def update_space_description(
        space_id: str,
        description: Annotated[str, Field(max_length=500)],
    ) -> dict[str, Any]:
        """Set a Space description after the user requests that change. An empty string clears it."""
        subject = await current_subject()
        payload = UpdateSpaceRequest(description=description)
        space = await _trove_result(spaces.update_space_for_user(space_id, subject, payload))
        return _serialize_tool_result({"space": space})

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
    )
    async def disconnect_trove() -> dict[str, bool]:
        """Revoke this connected app's Trove OAuth grant and sessions when the user asks to disconnect."""
        token = get_access_token()
        if token is None:
            raise ValueError("A valid Trove account link is required.")
        await _trove_result(supabase_auth.oauth_revoke_grant(token.token, oauth_client_id(token)))
        return _serialize_tool_result({"disconnected": True})
