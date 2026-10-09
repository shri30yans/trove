"""The typed read models, checked against the columns they read and the client that consumes them.

The Expo client declares its own Memory types in Zod, so a field renamed on one side and not the other
used to arrive as an undefined in the UI. These tests read a row the way the queries return it, encode
the model the way the API does, and hand the result to that client schema.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest
from pydantic import ValidationError

from app.errors import dump_json
from app.serialize import MemoryAsset, MemoryCard, MemoryDetail, MemoryListItem, MemoryListPage, MemorySpace

MEMORY = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
SPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
ASSET = uuid.UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")
NOW = dt.datetime(2026, 3, 4, 5, 6, 7, 8000, tzinfo=dt.UTC)
WIRE_STAMP = "2026-03-04T05:06:07.008Z"
# Postgres renders a timestamp inside json_build_object itself, so it reaches the API as text.
JSON_STAMP = "2026-03-04T05:06:07.008000+00:00"

CARD_ROW = {
    "id": MEMORY,
    "kind": "link",
    "status": "ready",
    "source_app": "Safari",
    "source_url": "https://example.test/a",
    "source_domain": "example.test",
    "title": "A page",
    "captured_at": NOW,
}
LIST_ROW = {
    **CARD_ROW,
    "description": "A description",
    "user_note": "A note",
    "page_text": None,
    "created_at": NOW,
    "preview_key": "users/synthetic/media/page.png",
}
DETAIL_ROW = {
    **LIST_ROW,
    "preview_key": None,
    "processing_error": None,
    "content_text": "Body text",
    "capture_metadata": {"device": "synthetic"},
    "occurred_at": None,
    "updated_at": NOW,
    "spaces": [{"id": str(SPACE), "name": "Reading", "color": None, "icon": None}],
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


def _wire(model: object) -> dict:
    """The payload exactly as it leaves the API: the response encoder, then parsed back."""
    return json.loads(dump_json(model))


def test_the_card_names_the_column_behind_every_field_it_renames() -> None:
    """The snake_case/camelCase border is where a silent undefined used to come from."""
    card = MemoryCard.from_row(CARD_ROW)
    assert card.id == str(MEMORY)
    assert card.sourceApp is CARD_ROW["source_app"]
    assert card.sourceUrl is CARD_ROW["source_url"]
    assert card.sourceDomain is CARD_ROW["source_domain"]
    assert card.capturedAt is CARD_ROW["captured_at"]


def test_a_projection_stops_when_its_query_stops_selecting_a_column() -> None:
    """No field is filled in behind the row's back: a dropped column fails at the read, not in the UI."""
    row = {key: value for key, value in CARD_ROW.items() if key != "source_domain"}
    with pytest.raises(KeyError):
        MemoryCard.from_row(row)


def test_an_status_the_domain_does_not_know_is_rejected() -> None:
    """`memory_status` is a Postgres enum; a value outside it means the two sides have drifted."""
    with pytest.raises(ValidationError):
        MemoryCard.from_row({**CARD_ROW, "status": "archived"})


def test_an_embedded_shape_rejects_a_column_the_json_query_added() -> None:
    """The Spaces and assets arrive as JSON the query shapes by hand, so their keys are checked too."""
    with pytest.raises(ValidationError):
        MemorySpace(id=str(SPACE), name="Reading", color=None, icon=None, memoryCount=3)


def test_a_built_response_cannot_be_edited_on_the_way_out() -> None:
    card = MemoryCard.from_row(CARD_ROW)
    with pytest.raises(ValidationError):
        card.title = "Rewritten"


def test_the_preview_is_handed_out_as_a_path_never_a_storage_key() -> None:
    page = MemoryListPage(memories=[MemoryListItem.from_row(LIST_ROW)], nextCursor=None)
    assert _wire(page)["memories"][0]["previewUrl"] == f"/v1/memories/{MEMORY}/preview"
    assert "users/synthetic" not in dump_json(page)


def test_an_attachment_carries_the_api_path_that_serves_its_bytes() -> None:
    asset = MemoryDetail.from_row(DETAIL_ROW).assets[0]
    assert asset.url == f"/v1/assets/{ASSET}/content"
    assert asset.createdAt == JSON_STAMP


def test_the_card_satisfies_the_mobile_runtime_contract(mobile_schema) -> None:
    result = mobile_schema("src/api/schemas/memories.ts", "memoryCardSchema", _wire(MemoryCard.from_row(CARD_ROW)))
    assert result["valid"], "The backend card no longer matches the mobile runtime schema"


def test_the_detail_satisfies_the_mobile_runtime_contract(mobile_schema) -> None:
    result = mobile_schema(
        "src/api/schemas/memories.ts", "memoryDetailSchema", _wire(MemoryDetail.from_row(DETAIL_ROW))
    )
    assert result["valid"], "The backend detail no longer matches the mobile runtime schema"


def test_the_list_page_satisfies_the_mobile_runtime_contract(mobile_schema) -> None:
    result = mobile_schema(
        "src/api/schemas/memories.ts",
        "memoryListResponseSchema",
        _wire(MemoryListPage(memories=[MemoryListItem.from_row(LIST_ROW)], nextCursor=None)),
    )
    assert result["valid"], "The backend list page no longer matches the mobile runtime schema"


def test_the_asset_satisfies_the_mobile_runtime_contract(mobile_schema) -> None:
    """The client checks the attachment's content path against its own identifier."""
    result = mobile_schema(
        "src/api/schemas/memories.ts", "assetSchema", _wire(MemoryAsset.from_json(DETAIL_ROW["assets"][0]))
    )
    assert result["valid"], "The backend asset no longer matches the mobile runtime schema"
