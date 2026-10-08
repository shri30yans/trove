"""parse_timestamp decides what the API accepts for capturedAt, after and before."""

from __future__ import annotations

import datetime as dt

import pytest

from app.errors import ApiError
from app.times import parse_timestamp

UTC = dt.UTC


def test_absent_and_blank_values_are_not_timestamps() -> None:
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None
    assert parse_timestamp("   ") is None


def test_zulu_suffix_is_accepted() -> None:
    assert parse_timestamp("2026-03-05T12:30:45.123Z") == dt.datetime(2026, 3, 5, 12, 30, 45, 123_000, UTC)


def test_lowercase_z_is_accepted() -> None:
    assert parse_timestamp("2026-03-05T12:30:45z") == dt.datetime(2026, 3, 5, 12, 30, 45, tzinfo=UTC)


def test_a_naive_value_is_read_as_utc() -> None:
    parsed = parse_timestamp("2026-03-05T12:30:45")
    assert parsed == dt.datetime(2026, 3, 5, 12, 30, 45, tzinfo=UTC)
    assert parsed is not None
    assert parsed.utcoffset() == dt.timedelta(0)


def test_an_offset_is_normalised_to_utc() -> None:
    parsed = parse_timestamp("2026-03-05T12:30:45+05:30")
    assert parsed == dt.datetime(2026, 3, 5, 7, 0, 45, tzinfo=UTC)


def test_a_date_without_a_time_is_midnight() -> None:
    assert parse_timestamp("2026-03-05") == dt.datetime(2026, 3, 5, tzinfo=UTC)


def test_unparseable_values_raise_a_400_with_the_callers_error_code() -> None:
    with pytest.raises(ApiError) as caught:
        parse_timestamp("yesterday", error_code="invalid_memory")
    assert caught.value.status_code == 400
    assert caught.value.code == "invalid_memory"
    assert "'yesterday'" in caught.value.message


def test_require_offset_rejects_a_naive_value() -> None:
    with pytest.raises(ApiError, match="needs a UTC offset"):
        parse_timestamp("2026-03-05T12:30:45", require_offset=True)


def test_require_offset_still_accepts_an_explicit_offset() -> None:
    parsed = parse_timestamp("2026-03-05T12:30:45.123456+00:00", require_offset=True)
    assert parsed == dt.datetime(2026, 3, 5, 12, 30, 45, 123_456, UTC)
