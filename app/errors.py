"""Shared error envelope and JSON serialization for the Trove API."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from typing import Any

from fastapi.responses import JSONResponse


def iso_milliseconds(value: Any) -> str:
    """Format a timestamp as the API emits it: UTC, millisecond precision, Z suffix."""
    moment = value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    moment = moment.astimezone(dt.UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def json_default(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return iso_milliseconds(value)
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dump_json(content: Any) -> str:
    return json.dumps(content, default=json_default, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class ApiJSONResponse(JSONResponse):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return dump_json(content).encode("utf-8")


def respond(content: object, status_code: int = 200) -> ApiJSONResponse:
    """Return a payload with the shared JSON encoding (UUIDs and ISO-Z timestamps)."""
    return ApiJSONResponse(content=content, status_code=status_code)


class ApiError(Exception):
    """An error that is reported to the client with an explicit code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def to_response(self) -> ApiJSONResponse:
        return ApiJSONResponse(
            status_code=self.status_code, content={"error": {"code": self.code, "message": self.message}}
        )


def not_found(message: str = "Route not found.") -> ApiError:
    return ApiError(404, "not_found", message)
