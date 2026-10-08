"""The shared Memory card shape, checked against the client that consumes it.

One function now spells the ten fields that the detail, list, search and related endpoints all
return. The Expo client declares its own Memory type, so a field renamed on one side and not the
other is a silent undefined in the UI rather than an error.
"""

from __future__ import annotations

import uuid

from app.serialize import memory_card

MEMORY_ID = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
ROW = {
    "id": MEMORY_ID,
    "kind": "link",
    "status": "ready",
    "source_app": "Safari",
    "source_url": "https://example.test/a",
    "source_domain": "example.test",
    "title": "A page",
    "captured_at": "2026-03-04T05:06:07.008Z",
}


def test_the_card_carries_the_shared_fields_and_nothing_else() -> None:
    assert memory_card(ROW) == {
        "id": str(MEMORY_ID),
        "kind": "link",
        "status": "ready",
        "sourceApp": "Safari",
        "sourceUrl": "https://example.test/a",
        "sourceDomain": "example.test",
        "title": "A page",
        "capturedAt": "2026-03-04T05:06:07.008Z",
    }


def test_each_card_field_comes_from_the_column_it_is_named_after() -> None:
    """A rename on one side of the snake_case/camelCase border is the bug this guard catches."""
    card = memory_card(ROW)
    assert card["sourceApp"] is ROW["source_app"]
    assert card["sourceUrl"] is ROW["source_url"]
    assert card["sourceDomain"] is ROW["source_domain"]
    assert card["capturedAt"] is ROW["captured_at"]


def test_the_actual_card_satisfies_the_mobile_runtime_contract(mobile_schema) -> None:
    result = mobile_schema("src/api/schemas/memories.ts", "memoryCardSchema", memory_card(ROW))
    assert result["valid"], "The backend card no longer matches the mobile runtime schema"
