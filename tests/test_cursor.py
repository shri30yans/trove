"""The memory page cursor is an opaque, client-carried (captured_at, id) keyset."""

from __future__ import annotations

import base64
import datetime as dt
import uuid

import pytest

from app.routes.memories import _decode_cursor, _encode_cursor

UTC = dt.UTC
MEMORY_ID = "11111111-2222-3333-4444-555555555555"


def test_a_cursor_round_trips_to_the_exact_keyset_position() -> None:
    captured_at = dt.datetime(2026, 3, 5, 12, 30, 45, 123_000, UTC)
    decoded = _decode_cursor(_encode_cursor(captured_at, MEMORY_ID))
    assert decoded == (captured_at, MEMORY_ID)


def test_the_cursor_carries_no_padding_character() -> None:
    token = _encode_cursor(dt.datetime(2026, 1, 1, tzinfo=UTC), MEMORY_ID)
    assert "=" not in token
    assert "+" not in token, "the cursor goes in a query string"
    assert "/" not in token


def test_absent_cursors_are_the_first_page() -> None:
    assert _decode_cursor(None) is None
    assert _decode_cursor("") is None


@pytest.mark.parametrize(
    "token",
    ["!!!not base64!!!", "aGVsbG8", base64.b64encode(b"no separator").decode(), "TG9yZW0=", "%s"],
)
def test_a_malformed_cursor_decodes_to_none_rather_than_raising(token: str) -> None:
    assert _decode_cursor(token) is None


def test_a_cursor_without_a_uuid_half_is_rejected() -> None:
    raw = "2026-03-05T12:30:45.123Z|not-a-uuid"
    assert _decode_cursor(base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")) is None


def test_a_cursor_with_an_unparseable_timestamp_is_rejected() -> None:
    raw = f"yesterday|{MEMORY_ID}"
    assert _decode_cursor(base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")) is None


def test_a_cursor_with_no_timestamp_is_rejected() -> None:
    raw = f"|{MEMORY_ID}"
    assert _decode_cursor(base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")) is None


def test_a_cursor_is_uuid_case_insensitive_because_postgres_emits_lowercase() -> None:
    upper = MEMORY_ID.upper()
    token = _encode_cursor(dt.datetime(2026, 1, 1, tzinfo=UTC), upper)
    decoded = _decode_cursor(token)
    assert decoded is not None
    assert uuid.UUID(decoded[1]) == uuid.UUID(MEMORY_ID)


def test_the_wire_format_of_the_keyset_is_the_shared_iso_z_milliseconds() -> None:
    token = _encode_cursor(dt.datetime(2026, 3, 5, 1, 2, 3, 4_000, UTC), MEMORY_ID)
    decoded = base64.urlsafe_b64decode(token + "==").decode()
    assert decoded.startswith("2026-03-05T01:02:03.004Z|")
