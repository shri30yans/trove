"""The Memory reads more than one surface needs.

An HTTP route, the MCP tool layer and every write that answers with the record it just saved all read
the same projections, so the SQL and its typed read model live here rather than behind a router. The
route modules keep what is theirs: the status codes, the ownership decisions made before a write, and
the transactions that own a change.

Each function names the columns it selects and builds the projection in one place, so a column rename
in the schema fails while the response is being assembled instead of arriving on the phone as a
missing field.
"""

from __future__ import annotations

import base64
import datetime as dt
import re
import uuid
from collections.abc import Mapping

from app.auth import Principal, as_uuid
from app.db import fetch, fetchrow
from app.domain.retrieval import LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT, LIST_MIN_LIMIT, parse_limit
from app.errors import ApiError, iso_milliseconds
from app.queries import PREVIEW_KEY_SUBQUERY
from app.schemas import parse_kind_param
from app.serialize import MemoryDetail, MemoryListItem, MemoryListPage
from app.times import parse_timestamp

_MEMORY_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def encode_cursor(captured_at: dt.datetime, memory_id: str) -> str:
    raw = f"{iso_milliseconds(captured_at)}|{memory_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(value: str | None) -> tuple[dt.datetime, str] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    separator = decoded.rfind("|")
    if separator < 0:
        return None
    memory_id = decoded[separator + 1 :]
    if not _MEMORY_ID.match(memory_id):
        return None
    try:
        captured_at = parse_timestamp(decoded[:separator])
    except ApiError:
        return None
    return (captured_at, memory_id) if captured_at else None


async def read_memory(user_id: uuid.UUID, memory_id: uuid.UUID, *, record_opened: bool = False) -> MemoryDetail | None:
    """One Memory's full projection, optionally recording that the user opened it.

    The open is written in the same statement as the read: `opened` and `opened_event` run against the
    materialized target, so a second round trip would either race the read or report an open the
    response does not contain.
    """
    memory = await fetchrow(
        """WITH target AS MATERIALIZED (
           SELECT m.id, m.kind, m.status, m.processing_error, m.source_app, m.source_url, m.source_domain,
             m.title, m.description, m.user_note, m.content_text, m.page_text,
             m.capture_metadata, m.captured_at, m.occurred_at, m.created_at, m.updated_at,
             COALESCE((SELECT json_agg(json_build_object('id',s.id,'name',s.name,'color',s.color,'icon',s.icon) ORDER BY s.name)
               FROM memory_spaces ms JOIN spaces s ON s.id=ms.space_id AND s.deleted_at IS NULL
               WHERE ms.memory_id=m.id AND ms.user_id=m.user_id), '[]'::json) AS spaces,
             COALESCE((SELECT json_agg(mt.tag ORDER BY mt.tag) FROM memory_tags mt WHERE mt.memory_id=m.id AND mt.user_id=m.user_id), '[]'::json) AS tags
           FROM memories m WHERE m.id=$1 AND m.user_id=$2 AND m.deleted_at IS NULL
         ), opened AS (
           UPDATE memories m SET last_opened_at=now()
           FROM target t
           WHERE $3::boolean AND m.id=t.id AND m.user_id=$2 AND m.deleted_at IS NULL
           RETURNING m.id, m.user_id
         ), opened_event AS (
           INSERT INTO memory_events(user_id,memory_id,event_type)
           SELECT o.user_id,o.id,'opened' FROM opened o
           RETURNING memory_id
         )
         SELECT t.*,
           COALESCE((SELECT json_agg(json_build_object('id',a.id,'filename',a.original_filename,
             'mimeType',a.mime_type,'byteSize',a.byte_size,'status',a.status,'createdAt',a.created_at,'role',ma.role)
             ORDER BY ma.position)
             FROM memory_assets ma JOIN assets a ON a.id=ma.asset_id AND a.user_id=ma.user_id
             WHERE ma.memory_id=t.id AND ma.user_id=$2), '[]'::json) AS assets
         FROM target t""",
        memory_id,
        user_id,
        record_opened,
    )
    if memory is None:
        return None
    return MemoryDetail.from_row(memory)


async def read_back(user_id: uuid.UUID, memory_id: uuid.UUID) -> MemoryDetail:
    """The response body for a Memory this route just wrote.

    Nothing answers with a null `memory`: the client's contract requires the object, so a row deleted
    between the write and this read is the same 404 any other missing Memory is.
    """
    memory = await read_memory(user_id, memory_id)
    if memory is None:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    return memory


async def get_memory_detail(
    memory_id: str,
    principal: Principal,
    *,
    record_opened: bool = False,
) -> MemoryDetail:
    """Read one caller-owned memory, optionally recording an in-app open event."""
    memory = await read_memory(uuid.UUID(principal.id), as_uuid(memory_id), record_opened=record_opened)
    if memory is None:
        raise ApiError(404, "memory_not_found", "Memory not found.")
    return memory


async def list_memories_for_user(principal: Principal, query: Mapping[str, str]) -> MemoryListPage:
    """List one caller's memories from plain query values, shared by HTTP and MCP."""
    limit = parse_limit(query.get("limit"), default=LIST_DEFAULT_LIMIT, minimum=LIST_MIN_LIMIT, maximum=LIST_MAX_LIMIT)
    kind = parse_kind_param(query.get("kind"))
    raw_cursor = query.get("cursor")
    cursor = decode_cursor(raw_cursor)
    if raw_cursor and cursor is None:
        raise ApiError(400, "invalid_cursor", "The page cursor is invalid.")
    after = parse_timestamp(query.get("after")) if query.get("after") else None
    before = parse_timestamp(query.get("before")) if query.get("before") else None
    user_id = uuid.UUID(principal.id)
    space_id = query.get("spaceId")
    rows = await fetch(
        f"""SELECT m.id, m.kind, m.status, m.source_app, m.source_url, m.source_domain, m.title,
            m.description, m.user_note, m.page_text, m.captured_at, m.created_at,
            {PREVIEW_KEY_SUBQUERY}
           FROM memories m
           WHERE m.user_id=$1 AND m.deleted_at IS NULL
             AND ($2::memory_kind IS NULL OR m.kind=$2::memory_kind)
             AND ($3::uuid IS NULL OR EXISTS (SELECT 1 FROM memory_spaces ms WHERE ms.memory_id=m.id AND ms.space_id=$3 AND ms.user_id=m.user_id))
             AND ($4::text IS NULL OR m.source_domain=$4)
             AND ($5::timestamptz IS NULL OR (m.captured_at,m.id)<($5::timestamptz,$6::uuid))
             AND ($8::timestamptz IS NULL OR m.captured_at >= $8::timestamptz)
             AND ($9::timestamptz IS NULL OR m.captured_at < $9::timestamptz)
           ORDER BY m.captured_at DESC, m.id DESC LIMIT $7""",
        user_id,
        kind,
        as_uuid(space_id) if space_id else None,
        query.get("source"),
        cursor[0] if cursor else None,
        uuid.UUID(cursor[1]) if cursor else None,
        limit + 1,
        after,
        before,
    )
    has_more = len(rows) > limit
    page = [MemoryListItem.from_row(row) for row in rows[:limit]]
    last = page[-1] if has_more and page else None
    return MemoryListPage(
        memories=page,
        nextCursor=encode_cursor(last.capturedAt, last.id) if last else None,
    )
