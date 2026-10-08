"""ISO-8601 timestamp parsing for the API's UTC millisecond wire format."""

from __future__ import annotations

import datetime as dt

from app.errors import ApiError


def parse_timestamp(
    value: str | None, *, error_code: str = "invalid_date", require_offset: bool = False
) -> dt.datetime | None:
    """Parse an ISO-8601 timestamp; a value without an offset is read as UTC unless required."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        moment = dt.datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ApiError(400, error_code, f"The date value {value!r} is invalid.") from error
    if moment.tzinfo is None:
        if require_offset:
            raise ApiError(400, error_code, f"The date value {value!r} needs a UTC offset.")
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(dt.UTC)
