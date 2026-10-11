"""The exact bytes every projection puts on the wire.

The Expo client validates these bodies with a runtime Zod schema, so a field that changes name,
format, or null-ness fails on the phone instead of in this API. Each expectation below was recorded
from the hand-built dictionaries that preceded the typed read models, so it is the contract the phone
receives rather than a description of the current code.

Timestamps travel in two forms and both are pinned here: a column the API encoder formats (ISO,
millisecond precision, `Z`) and a value Postgres rendered inside `json_build_object` (ISO, microsecond
precision, `+00:00`). The client's schema accepts either.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app import memory_reads
from app.auth import Principal, VerifiedSubject
from app.embedding import embeddings
from app.errors import dump_json
from app.routes import accounts, memories, search, spaces

USER = uuid.UUID("00000000-0000-4000-8000-000000000001")
MEMORY = uuid.UUID("00000000-0000-4000-8000-000000000002")
SECOND = uuid.UUID("00000000-0000-4000-8000-000000000009")
ASSET = uuid.UUID("00000000-0000-4000-8000-000000000003")
SPACE = uuid.UUID("00000000-0000-4000-8000-000000000004")
NOW = dt.datetime(2026, 3, 4, 5, 6, 7, 8000, tzinfo=dt.UTC)
JSON_STAMP = "2026-03-04T05:06:07.008000+00:00"
WIRE_STAMP = "2026-03-04T05:06:07.008Z"
PREVIEW_KEY = "users/synthetic/media/page.png"

LIST_ROW = {
    "id": MEMORY,
    "kind": "link",
    "status": "ready",
    "source_app": "Safari",
    "source_url": "https://example.test/a?x=1",
    "source_domain": "example.test",
    "title": "A page",
    "captured_at": NOW,
    "description": "A description",
    "user_note": "A note",
    "page_text": "Extracted text",
    "created_at": NOW,
    "preview_key": PREVIEW_KEY,
}
# A Memory saved without a link, a title, or an image: every optional column is null.
BLANK_ROW = {
    **LIST_ROW,
    "id": SECOND,
    "kind": "text",
    "status": "queued",
    "source_app": None,
    "source_url": None,
    "source_domain": None,
    "title": None,
    "description": None,
    "user_note": None,
    "page_text": None,
    "preview_key": None,
}
DETAIL_ROW = {
    **LIST_ROW,
    "processing_error": None,
    "content_text": "Body text",
    "capture_metadata": {"device": "synthetic", "seenAt": JSON_STAMP, "frames": 3},
    "occurred_at": NOW,
    "updated_at": NOW,
    "spaces": [{"id": str(SPACE), "name": "Reading", "color": "#101010", "icon": "book"}],
    "tags": ["reading"],
    "assets": [
        {
            "id": str(ASSET),
            "filename": "page.html",
            "mimeType": "text/html",
            "byteSize": 16,
            "status": "attached",
            "createdAt": JSON_STAMP,
            "role": "original",
        }
    ],
}
SEARCH_ROW = {**LIST_ROW, "score": 1.5, "lexical_score": 0.25, "semantic_score": 0.75, "match_excerpt": "an excerpt"}
RELATED_ROW = {
    "id": SECOND,
    "kind": "image",
    "status": "ready",
    "source_app": "Camera",
    "source_url": None,
    "source_domain": None,
    "title": "A photo",
    "captured_at": NOW,
    "similarity": 0.91,
    "preview_key": None,
}
SPACE_ROW = {
    "id": SPACE,
    "name": "Reading",
    "description": "Things to read",
    "color": "#101010",
    "icon": "book",
    "created_at": NOW,
    "updated_at": NOW,
    "memory_count": 3,
}
UPDATE_ROW = {
    "id": MEMORY,
    "kind": "link",
    "status": "ready",
    "source_app": "Safari",
    "source_url": "https://example.test/a?x=1",
    "source_domain": "example.test",
    "title": "A page",
    "captured_at": NOW,
    "related_id": SECOND,
    "related_title": "A newer page",
    "related_captured_at": NOW,
    "similarity": 0.82,
    "preview_key": PREVIEW_KEY,
}

CARD_JSON = (
    f'"id":"{MEMORY}","kind":"link","status":"ready","sourceApp":"Safari",'
    '"sourceUrl":"https://example.test/a?x=1","sourceDomain":"example.test",'
    f'"title":"A page","capturedAt":"{WIRE_STAMP}"'
)

MODEL_SET = type("ModelSet", (), {"space_id": "synthetic-space"})()


@pytest.fixture
def principal() -> Principal:
    return Principal(id=str(USER), subject="synthetic", embeddings_enabled=False)


async def test_memory_detail_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        memory_reads,
        "fetchrow",
        AsyncMock(return_value={**DETAIL_ROW, "deleted": False, "deletion_pending": False, "user_id": USER}),
    )

    body = (await memories.get_memory(str(MEMORY), VerifiedSubject(subject="synthetic"))).body.decode()

    assert body == (
        '{"memory":{' + CARD_JSON + ',"processingError":null,"description":"A description","userNote":"A note",'
        '"contentText":"Body text","pageText":"Extracted text","captureMetadata":{"device":"synthetic",'
        f'"seenAt":"{JSON_STAMP}","frames":3}},"occurredAt":"{WIRE_STAMP}","createdAt":"{WIRE_STAMP}",'
        f'"updatedAt":"{WIRE_STAMP}","spaces":[{{"id":"{SPACE}","name":"Reading","color":"#101010",'
        f'"icon":"book"}}],"tags":["reading"],"assets":[{{"id":"{ASSET}","filename":"page.html","mimeType":"text/html",'
        f'"byteSize":16,"status":"attached","role":"original","createdAt":"{JSON_STAMP}",'
        f'"url":"/v1/assets/{ASSET}/content"}}]}}'
        "}"
    )


async def test_memory_list_page_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        memory_reads,
        "fetch",
        AsyncMock(
            return_value=[
                {"deleted": False, "deletion_pending": False, "user_id": USER, **LIST_ROW},
                {"deleted": False, "deletion_pending": False, "user_id": USER, **BLANK_ROW},
            ]
        ),
    )

    page = await memory_reads.list_memories_for_user(VerifiedSubject(subject="synthetic"), {"limit": "5"})

    blank = (
        f'"id":"{SECOND}","kind":"text","status":"queued","sourceApp":null,"sourceUrl":null,'
        f'"sourceDomain":null,"title":null,"capturedAt":"{WIRE_STAMP}","description":null,'
        f'"userNote":null,"pageText":null,"createdAt":"{WIRE_STAMP}","previewUrl":null'
    )
    assert dump_json(page) == (
        '{"memories":[{' + CARD_JSON + ',"description":"A description","userNote":"A note","pageText":"Extracted text",'
        f'"createdAt":"{WIRE_STAMP}","previewUrl":"/v1/memories/{MEMORY}/preview"}},{{{blank}}}],'
        '"nextCursor":null}'
    )


async def test_a_full_page_names_the_row_to_resume_from(principal: Principal, monkeypatch: pytest.MonkeyPatch) -> None:
    """The cursor is the wire timestamp and the identifier, base64url without padding."""
    monkeypatch.setattr(
        memory_reads,
        "fetch",
        AsyncMock(
            return_value=[
                {"deleted": False, "deletion_pending": False, "user_id": USER, **LIST_ROW},
                {"deleted": False, "deletion_pending": False, "user_id": USER, **BLANK_ROW},
            ]
        ),
    )

    page = await memory_reads.list_memories_for_user(VerifiedSubject(subject="synthetic"), {"limit": "1"})

    assert dump_json(page) == (
        '{"memories":[{' + CARD_JSON + ',"description":"A description","userNote":"A note",'
        '"pageText":"Extracted text",'
        f'"createdAt":"{WIRE_STAMP}","previewUrl":"/v1/memories/{MEMORY}/preview"}}],'
        '"nextCursor":"MjAyNi0wMy0wNFQwNTowNjowNy4wMDhafDAwMDAwMDAwLTAwMDAtNDAwMC04MDAwLTAwMDAwMDAwMDAwMg"}'
    )


async def test_search_result_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        search,
        "fetchrow",
        AsyncMock(
            return_value={"deleted": False, "deletion_pending": False, "user_id": USER, "embeddings_enabled": False}
        ),
    )
    monkeypatch.setattr(
        search,
        "fetch",
        AsyncMock(return_value=[{"deleted": False, "deletion_pending": False, "user_id": USER, **SEARCH_ROW}]),
    )

    results = await search.search_memories_for_user(VerifiedSubject(subject="synthetic"), {"q": "page"})

    assert dump_json(results) == (
        '{"query":"page","semanticSearch":false,"memories":[{'
        + CARD_JSON
        + ',"description":"A description","userNote":"A note","pageText":"Extracted text",'
        '"score":1.5,"matchType":"text_and_meaning","matchExcerpt":"an excerpt",'
        f'"previewUrl":"/v1/memories/{MEMORY}/preview"}}]}}'
    )


async def test_related_memory_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "models", lambda: MODEL_SET)
    fetch = AsyncMock(
        return_value=[
            {
                "deleted": False,
                "deletion_pending": False,
                "user_id": USER,
                "memory_exists": True,
                "embeddings_enabled": True,
                **RELATED_ROW,
            }
        ]
    )
    monkeypatch.setattr(search, "fetch", fetch)

    body = (await search.related_memories(str(MEMORY), VerifiedSubject(subject="synthetic"))).body.decode()

    fetch.assert_awaited_once()
    assert "vector_hits AS" in fetch.await_args.args[0]
    assert "memory_relation_feedback" in fetch.await_args.args[0]
    assert fetch.await_args.args[1:4] == ("synthetic", None, None)
    assert fetch.await_args.args[4] == MEMORY

    assert body == (
        f'{{"memories":[{{"id":"{SECOND}","kind":"image","status":"ready","sourceApp":"Camera",'
        '"sourceUrl":null,"sourceDomain":null,"title":"A photo",'
        f'"capturedAt":"{WIRE_STAMP}","similarity":0.91,"relation":"similar_idea",'
        '"reason":"Similar meaning or image","previewUrl":null}]}'
    )


async def test_space_list_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        spaces,
        "fetch",
        AsyncMock(return_value=[{**SPACE_ROW, "deleted": False, "deletion_pending": False, "user_id": USER}]),
    )

    assert dump_json(await spaces.list_spaces_for_user(VerifiedSubject(subject="synthetic"))) == (
        f'{{"spaces":[{{"id":"{SPACE}","name":"Reading","description":"Things to read",'
        f'"color":"#101010","icon":"book","createdAt":"{WIRE_STAMP}","updatedAt":"{WIRE_STAMP}",'
        '"memoryCount":3}]}'
    )


async def test_a_space_write_reports_no_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """The list query's join is the only source of a count, so a written Space cannot carry one."""
    row: dict[str, Any] = {
        **{key: value for key, value in SPACE_ROW.items() if key != "memory_count"},
        "deleted": False,
        "deletion_pending": False,
        "user_id": USER,
    }
    monkeypatch.setattr(spaces, "fetchrow", AsyncMock(return_value=row))

    from app.schemas import UpdateSpaceRequest

    space = await spaces.update_space_for_user(
        str(SPACE), VerifiedSubject(subject="synthetic"), UpdateSpaceRequest(name="Renamed")
    )

    assert dump_json({"space": space}) == (
        f'{{"space":{{"id":"{SPACE}","name":"Reading","description":"Things to read",'
        f'"color":"#101010","icon":"book","createdAt":"{WIRE_STAMP}","updatedAt":"{WIRE_STAMP}"}}}}'
    )


async def test_resurfacing_update_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        accounts,
        "fetchrow",
        AsyncMock(
            return_value={
                "deleted": False,
                "deletion_pending": False,
                "user_id": USER,
                "resurfacing_enabled": True,
                "resurfacing_cadence": "weekly",
                "embeddings_enabled": True,
            }
        ),
    )
    monkeypatch.setattr(embeddings, "models", lambda: MODEL_SET)
    monkeypatch.setattr(
        accounts,
        "find_resurfacing_memories",
        AsyncMock(return_value=[{"memoryId": str(MEMORY), "relatedId": str(SECOND), "similarity": 0.82}]),
    )
    monkeypatch.setattr(accounts, "fetch", AsyncMock(return_value=[UPDATE_ROW]))

    body = (await accounts.updates(VerifiedSubject(subject="synthetic"))).body.decode()

    assert body == (
        '{"enabled":true,"cadence":"weekly","updates":[{"memory":{'
        f'"id":"{MEMORY}","kind":"link","status":"ready","sourceApp":"Safari","sourceUrl":"https://example.test/a?x=1",'
        f'"sourceDomain":"example.test","title":"A page","capturedAt":"{WIRE_STAMP}",'
        f'"previewUrl":"/v1/memories/{MEMORY}/preview"}},"relatedTo":{{"id":"{SECOND}",'
        f'"title":"A newer page","capturedAt":"{WIRE_STAMP}"}},'
        '"reason":"Related to a newer Memory in your Trove","similarity":0.82}]}'
    )


async def test_preferences_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        accounts,
        "fetchrow",
        AsyncMock(
            return_value={
                "deleted": False,
                "deletion_pending": False,
                "user_id": USER,
                "resurfacing_enabled": True,
                "resurfacing_cadence": "monthly",
                "embeddings_enabled": True,
                "updated_at": NOW,
            }
        ),
    )

    body = (await accounts.get_preferences(VerifiedSubject(subject="synthetic"))).body.decode()

    assert body == (
        '{"preferences":{"resurfacingEnabled":true,"resurfacingCadence":"monthly","embeddingsEnabled":true,'
        f'"embeddingsAvailable":true,"updatedAt":"{WIRE_STAMP}"'
        "}}"
    )


async def test_unsaved_preferences_are_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no row there is no `updatedAt` to name, so the API reports only the defaults it applied."""
    monkeypatch.setattr(
        accounts,
        "fetchrow",
        AsyncMock(
            return_value={
                "deleted": False,
                "deletion_pending": False,
                "user_id": USER,
                "resurfacing_enabled": None,
                "resurfacing_cadence": None,
                "embeddings_enabled": None,
                "updated_at": None,
            }
        ),
    )

    body = (await accounts.get_preferences(VerifiedSubject(subject="synthetic"))).body.decode()

    assert body == (
        '{"preferences":{"resurfacingEnabled":false,"resurfacingCadence":"weekly","embeddingsEnabled":false,'
        '"embeddingsAvailable":true}}'
    )
