"""The wire format is a contract with the Expo client: ISO-Z milliseconds, UUID strings, no NaN."""

from __future__ import annotations

import datetime as dt
import decimal
import math
import uuid
from typing import Any

import pytest

from app.errors import ApiError, dump_json, iso_milliseconds, json_default, not_found, respond


def test_iso_milliseconds_uses_utc_and_three_decimals() -> None:
    moment = dt.datetime(2026, 3, 5, 12, 30, 45, 123_400, tzinfo=dt.UTC)
    assert iso_milliseconds(moment) == "2026-03-05T12:30:45.123Z"


def test_iso_milliseconds_truncates_instead_of_rounding() -> None:
    moment = dt.datetime(2026, 1, 1, tzinfo=dt.UTC, microsecond=999_999)
    assert iso_milliseconds(moment) == "2026-01-01T00:00:00.999Z"


def test_iso_milliseconds_reads_a_naive_timestamp_as_utc() -> None:
    moment = dt.datetime(2026, 3, 5, 1, 2, 3, 4_000)
    assert iso_milliseconds(moment) == "2026-03-05T01:02:03.004Z"


def test_iso_milliseconds_converts_a_non_utc_offset() -> None:
    plus_five = dt.timezone(dt.timedelta(hours=5))
    moment = dt.datetime(2026, 3, 5, 3, 0, 0, tzinfo=plus_five)
    assert iso_milliseconds(moment) == "2026-03-04T22:00:00.000Z"


def test_json_default_encodes_the_stored_value_types() -> None:
    identifier = uuid.UUID("11111111-2222-3333-4444-555555555555")
    assert json_default(identifier) == "11111111-2222-3333-4444-555555555555"
    assert json_default(decimal.Decimal("1.5")) == 1.5
    assert json_default(dt.date(2026, 3, 5)) == "2026-03-05"
    assert json_default(b"bytes") == "bytes"


def test_json_default_rejects_an_unencodable_object() -> None:
    with pytest.raises(TypeError):
        json_default(object())


def test_dump_json_keeps_keys_and_rejects_nan() -> None:
    assert dump_json({"b": 1, "a": [1, 2]}) == '{"b":1,"a":[1,2]}'
    assert dump_json({"emoji": "café ✓"}) == '{"emoji":"café ✓"}'
    with pytest.raises(ValueError):
        dump_json({"value": math.nan})


def test_api_error_renders_the_documented_envelope() -> None:
    error = ApiError(409, "memory_not_retryable", "Only failed Memories can be retried.")
    response = error.to_response()
    assert response.status_code == 409
    assert response.body == (
        b'{"error":{"code":"memory_not_retryable","message":"Only failed Memories can be retried."}}'
    )


def test_not_found_is_a_404_with_a_default_message() -> None:
    error = not_found()
    assert (error.status_code, error.code) == (404, "not_found")
    assert error.message == "Route not found."


def test_respond_encodes_datetimes_and_uuids_in_one_pass() -> None:
    payload: dict[str, Any] = {
        "capturedAt": dt.datetime(2026, 3, 5, 12, 0, 0, 500_000, tzinfo=dt.UTC),
        "id": uuid.UUID(int=1),
    }
    response = respond(payload, 201)
    assert response.status_code == 201
    assert response.body == b'{"capturedAt":"2026-03-05T12:00:00.500Z","id":"00000000-0000-0000-0000-000000000001"}'
