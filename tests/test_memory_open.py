import datetime as dt
import uuid
from unittest.mock import AsyncMock

import pytest

from app import memory_reads
from app.errors import ApiError
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
    from app.auth import VerifiedSubject

    fetch = AsyncMock(return_value=[{"deleted": False, "deletion_pending": False, "user_id": USER, "id": None}])
    monkeypatch.setattr(memory_reads, "fetch", fetch)

    result = await memory_reads.list_memories_for_user(
        VerifiedSubject(subject="synthetic"),
        {"limit": "4", "spaceId": str(MEMORY), "kind": "text"},
    )

    assert result == MemoryListPage(memories=[], nextCursor=None)
    assert fetch.await_args.args[1:4] == ("synthetic", None, None)
    assert fetch.await_args.args[4] == "text"
    assert fetch.await_args.args[5] == MEMORY
    assert fetch.await_args.args[9] == 5


async def test_memory_open_for_subject_resolves_account_and_reads_in_one_round_trip(monkeypatch):
    from app.auth import VerifiedSubject

    row = {
        "deleted": False,
        "deletion_pending": False,
        "user_id": USER,
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
    fetchrow = AsyncMock(return_value=row)
    monkeypatch.setattr(memory_reads, "fetchrow", fetchrow)

    result = await memory_reads.get_memory_detail_for_subject(
        str(MEMORY), VerifiedSubject(subject="synthetic-subject"), record_opened=True
    )

    assert result.id == str(MEMORY)
    fetchrow.assert_awaited_once()
    query, subject, email, display_name, memory_id, record_opened = fetchrow.call_args.args
    assert subject == "synthetic-subject"
    assert memory_id == MEMORY
    assert record_opened is True
    # The auth preamble and the memory read share this one statement.
    assert "FROM deleted_auth_subjects WHERE auth_subject=$1" in query
    assert "INSERT INTO app_users (auth_subject, email, display_name)" in query
    assert "m.id=$4 AND m.user_id=a.user_id AND m.deleted_at IS NULL" in query
    assert "UPDATE memories m SET last_opened_at=now()" in query
    assert "INSERT INTO memory_events" in query
    assert "FROM auth LEFT JOIN target t ON TRUE" in query


async def test_memory_open_for_subject_reports_missing_as_none(monkeypatch):
    row = {"deleted": False, "deletion_pending": False, "user_id": USER, "id": None}
    fetchrow = AsyncMock(return_value=row)
    monkeypatch.setattr(memory_reads, "fetchrow", fetchrow)

    assert (
        await memory_reads.read_memory_for_subject("synthetic-subject", None, None, MEMORY, record_opened=True) is None
    )


async def test_memory_open_for_subject_keeps_not_found_behavior(monkeypatch):
    from app.auth import VerifiedSubject

    fetchrow = AsyncMock(return_value={"deleted": False, "deletion_pending": False, "user_id": USER, "id": None})
    monkeypatch.setattr(memory_reads, "fetchrow", fetchrow)

    with pytest.raises(ApiError) as error:
        await memory_reads.get_memory_detail_for_subject(str(MEMORY), VerifiedSubject(subject="synthetic-subject"))

    assert error.value.code == "memory_not_found"


async def test_memory_open_for_subject_rejects_deleted_and_pending_accounts(monkeypatch):
    fetchrow = AsyncMock(return_value={"deleted": True, "deletion_pending": False, "user_id": USER, "id": None})
    monkeypatch.setattr(memory_reads, "fetchrow", fetchrow)
    with pytest.raises(ApiError) as error:
        await memory_reads.read_memory_for_subject("tombstoned", None, None, MEMORY)
    assert error.value.code == "account_deleted"

    fetchrow = AsyncMock(return_value={"deleted": False, "deletion_pending": True, "user_id": USER, "id": None})
    monkeypatch.setattr(memory_reads, "fetchrow", fetchrow)
    with pytest.raises(ApiError) as error:
        await memory_reads.read_memory_for_subject("pending", None, None, MEMORY)
    assert error.value.code == "account_deletion_pending"


async def test_require_subject_verifies_token_without_touching_the_database(monkeypatch):
    from app import auth as auth_module

    async def _no_db(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("require_subject must not touch the database")

    monkeypatch.setattr(auth_module, "fetchrow", _no_db)
    monkeypatch.setattr(auth_module, "verify_bearer_token", AsyncMock(return_value={"sub": "synthetic-subject"}))

    class _Request:
        headers = {"authorization": "Bearer synthetic-token"}

    subject = await auth_module.require_subject(_Request())  # type: ignore[arg-type]

    assert subject.subject == "synthetic-subject"


async def test_related_memory_eligibility_checks_ownership_and_ai_in_one_round_trip(monkeypatch):
    from app.auth import VerifiedSubject
    from app.routes import search

    fetch = AsyncMock(
        return_value=[
            {
                "deleted": False,
                "deletion_pending": False,
                "user_id": USER,
                "memory_exists": True,
                "embeddings_enabled": False,
                "id": None,
            }
        ]
    )
    monkeypatch.setattr(search, "fetch", fetch)

    await search.related_memories(str(MEMORY), VerifiedSubject(subject="synthetic"))

    fetch.assert_awaited_once()
    query = fetch.await_args.args[0]
    assert fetch.await_args.args[1:4] == ("synthetic", None, None)
    assert fetch.await_args.args[4] == MEMORY
    assert "FROM memories WHERE id=$4 AND user_id=(SELECT user_id FROM auth)" in query
    assert "FROM user_preferences WHERE user_id=(SELECT user_id FROM auth)" in query
    assert "LEFT JOIN filtered_hits" in query


async def test_related_memory_keeps_not_found_behavior_in_single_query(monkeypatch):
    from app.auth import VerifiedSubject
    from app.routes import search

    fetch = AsyncMock(
        return_value=[
            {
                "deleted": False,
                "deletion_pending": False,
                "user_id": USER,
                "memory_exists": False,
                "embeddings_enabled": False,
                "id": None,
            }
        ]
    )
    monkeypatch.setattr(search, "fetch", fetch)

    with pytest.raises(ApiError) as error:
        await search.related_memories(str(MEMORY), VerifiedSubject(subject="synthetic"))

    assert error.value.code == "memory_not_found"
    fetch.assert_awaited_once()
