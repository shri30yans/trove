import datetime as dt
import uuid
from unittest.mock import AsyncMock

from app import memory_reads
from app.serialize import MemoryAsset, MemoryListPage

USER = uuid.UUID("00000000-0000-4000-8000-000000000001")
MEMORY = uuid.UUID("00000000-0000-4000-8000-000000000002")
ASSET = uuid.UUID("00000000-0000-4000-8000-000000000003")
NOW = dt.datetime(2026, 10, 7, tzinfo=dt.UTC)
# What Postgres itself renders for a timestamp inside json_build_object, verified against the live pooler.
JSON_STAMP = "2026-10-07T00:00:00.000000+00:00"


async def test_memory_detail_reads_assets_and_records_open_in_one_database_round_trip(monkeypatch):
    row = {
        "id": MEMORY,
        "kind": "text",
        "status": "ready",
        "processing_error": None,
        "source_app": "Trove",
        "source_url": None,
        "source_domain": None,
        "title": "A synthetic memory",
        "description": "Synthetic fixture",
        "user_note": None,
        "content_text": "Synthetic fixture",
        "page_text": None,
        "capture_metadata": {},
        "captured_at": NOW,
        "occurred_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "spaces": [],
        "tags": ["synthetic"],
        "assets": [
            {
                "id": ASSET,
                "filename": "synthetic.txt",
                "mimeType": "text/plain",
                "byteSize": 16,
                "status": "attached",
                "createdAt": JSON_STAMP,
                "role": "attachment",
            }
        ],
    }
    fetchrow = AsyncMock(return_value=row)
    fetch = AsyncMock()
    monkeypatch.setattr(memory_reads, "fetchrow", fetchrow)
    monkeypatch.setattr(memory_reads, "fetch", fetch)

    result = await memory_reads.read_memory(USER, MEMORY, record_opened=True)

    assert fetchrow.await_count == 1
    query, memory_id, user_id, record_opened = fetchrow.call_args.args
    assert memory_id == MEMORY
    assert user_id == USER
    assert record_opened is True
    assert "m.id=$1 AND m.user_id=$2 AND m.deleted_at IS NULL" in query
    assert "UPDATE memories" in query
    assert "INSERT INTO memory_events" in query
    assert "FROM memory_assets ma JOIN assets a" in query
    fetch.assert_not_awaited()
    assert result.assets == [
        MemoryAsset(
            id=str(ASSET),
            filename="synthetic.txt",
            mimeType="text/plain",
            byteSize=16,
            status="attached",
            role="attachment",
            createdAt=JSON_STAMP,
            url=f"/v1/assets/{ASSET}/content",
        )
    ]


async def test_memory_detail_query_does_not_record_open_for_non_open_callers(monkeypatch):
    fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(memory_reads, "fetchrow", fetchrow)

    result = await memory_reads.read_memory(USER, MEMORY)

    assert result is None
    query, _, _, record_opened = fetchrow.call_args.args
    assert record_opened is False
    assert "WHERE $3::boolean AND m.id=t.id" in query


async def test_mcp_memory_detail_reads_without_recording_an_open(monkeypatch):
    from app.auth import Principal

    fetchrow = AsyncMock(
        return_value={
            "id": MEMORY,
            "kind": "text",
            "status": "ready",
            "processing_error": None,
            "source_app": "Trove",
            "source_url": None,
            "source_domain": None,
            "title": "A synthetic memory",
            "description": "Synthetic fixture",
            "user_note": None,
            "content_text": "Synthetic fixture",
            "page_text": None,
            "capture_metadata": {},
            "captured_at": NOW,
            "occurred_at": None,
            "created_at": NOW,
            "updated_at": NOW,
            "spaces": [],
            "tags": [],
            "assets": [],
        }
    )
    monkeypatch.setattr(memory_reads, "fetchrow", fetchrow)

    result = await memory_reads.get_memory_detail(
        str(MEMORY), Principal(id=str(USER), subject="synthetic", embeddings_enabled=False)
    )

    assert result.id == str(MEMORY)
    query, _, _, record_opened = fetchrow.call_args.args
    assert record_opened is False
    assert "UPDATE memories" in query
    assert "INSERT INTO memory_events" in query


async def test_memory_list_service_accepts_plain_query_values(monkeypatch):
    from app.auth import Principal

    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(memory_reads, "fetch", fetch)

    result = await memory_reads.list_memories_for_user(
        Principal(id=str(USER), subject="synthetic", embeddings_enabled=False),
        {"limit": "4", "spaceId": str(MEMORY), "kind": "text"},
    )

    assert result == MemoryListPage(memories=[], nextCursor=None)
    assert fetch.await_args.args[1] == USER
    assert fetch.await_args.args[2] == "text"
    assert fetch.await_args.args[3] == MEMORY
    assert fetch.await_args.args[7] == 5


async def test_related_memory_eligibility_checks_ownership_and_ai_in_one_round_trip(monkeypatch):
    from app.auth import Principal
    from app.routes import search

    fetchrow = AsyncMock(return_value={"memory_exists": True, "embeddings_enabled": False})
    monkeypatch.setattr(search, "fetchrow", fetchrow)

    await search.related_memories(str(MEMORY), Principal(id=str(USER), subject="synthetic", embeddings_enabled=False))

    assert fetchrow.await_count == 1
    query, target, user_id = fetchrow.call_args.args
    assert target == MEMORY
    assert user_id == USER
    assert "FROM memories WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL" in query
    assert "FROM user_preferences WHERE user_id=$2" in query
