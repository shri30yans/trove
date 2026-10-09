"""Space responses share one shape.

The client appends a created Space straight onto the list it rendered from GET /v1/spaces, so a
second spelling of the same entity lands in the same array: the list serialised through _as_space and
the write routes returned the raw row, which is snake_case and carries no memory count.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

import pytest

from app.auth import VerifiedSubject
from app.errors import ApiError
from app.routes import spaces

SPACE_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
USER_ID = uuid.UUID("55555555-5555-5555-8555-555555555555")
CREATED_AT = dt.datetime(2026, 3, 4, 5, 6, 7, 8000, tzinfo=dt.UTC)

WRITE_KEYS = {"id", "name", "description", "color", "icon", "createdAt", "updatedAt"}

SUBJECT = VerifiedSubject(subject="subject-1", email="t@example.com", display_name="T")


def row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "deleted": False,
        "deletion_pending": False,
        "user_id": USER_ID,
        "id": SPACE_ID,
        "name": "Reading",
        "description": None,
        "color": "#123456",
        "icon": "book",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    return {**base, **overrides}


def body_of(response: Any) -> dict[str, Any]:
    return json.loads(response.body)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_fetchrow(sql: str, *args: Any) -> Any:
        calls.append((" ".join(sql.split()), args))
        return row()

    async def fake_fetch(sql: str, *args: Any) -> list[Any]:
        calls.append((" ".join(sql.split()), args))
        return [row(memory_count=3)]

    monkeypatch.setattr(spaces, "fetchrow", fake_fetchrow)
    monkeypatch.setattr(spaces, "fetch", fake_fetch)
    return calls


class Body:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def json(self) -> dict[str, Any]:
        return self.payload


async def test_the_list_reports_each_space_and_its_count(recorded: list[Any]) -> None:
    space = body_of(await spaces.list_spaces(SUBJECT))["spaces"][0]
    assert set(space) == WRITE_KEYS | {"memoryCount"}
    assert space["memoryCount"] == 3
    assert space["id"] == str(SPACE_ID)
    assert space["createdAt"] == "2026-03-04T05:06:07.008Z"


async def test_a_created_space_is_spelled_like_a_listed_one(recorded: list[Any]) -> None:
    response = await spaces.create_space(Body({"name": "Reading"}), SUBJECT)  # type: ignore[arg-type]
    space = body_of(response)["space"]
    assert set(space) == WRITE_KEYS
    assert response.status_code == 201


async def test_an_updated_space_is_spelled_like_a_listed_one(recorded: list[Any]) -> None:
    space = body_of(await spaces.update_space(Body({"color": "#abcdef"}), str(SPACE_ID), SUBJECT))["space"]  # type: ignore[arg-type]
    assert set(space) == WRITE_KEYS


async def test_a_write_does_not_claim_a_memory_count_it_never_read(recorded: list[Any]) -> None:
    # Reporting zero would be a guess: an update leaves the count wherever it already was.
    space = body_of(await spaces.create_space(Body({"name": "Reading"}), SUBJECT))["space"]  # type: ignore[arg-type]
    assert "memoryCount" not in space


async def test_the_list_resolves_the_account_in_its_own_round_trip(recorded: list[Any]) -> None:
    await spaces.list_spaces(SUBJECT)
    statement, args = recorded[0]
    assert "FROM deleted_auth_subjects WHERE auth_subject=$1" in statement
    assert "INSERT INTO app_users (auth_subject, email, display_name)" in statement
    assert args[:3] == ("subject-1", "t@example.com", "T")
    assert "LEFT JOIN LATERAL" in statement


async def test_a_missing_space_is_still_a_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetchrow(sql: str, *args: Any) -> Any:
        return row(id=None)

    monkeypatch.setattr(spaces, "fetchrow", fake_fetchrow)
    with pytest.raises(ApiError) as error:
        await spaces.update_space(Body({"color": "#abcdef"}), str(SPACE_ID), SUBJECT)  # type: ignore[arg-type]
    assert error.value.code == "space_not_found"


async def test_a_deleted_subject_cannot_list_or_write(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(sql: str, *args: Any) -> list[Any]:
        return [row(id=None, memory_count=None, deleted=True)]

    async def fake_fetchrow(sql: str, *args: Any) -> Any:
        return row(id=None, deleted=True)

    monkeypatch.setattr(spaces, "fetch", fake_fetch)
    monkeypatch.setattr(spaces, "fetchrow", fake_fetchrow)
    with pytest.raises(ApiError) as error:
        await spaces.list_spaces(SUBJECT)
    assert error.value.code == "account_deleted"
    with pytest.raises(ApiError) as error:
        await spaces.delete_space(str(SPACE_ID), SUBJECT)
    assert error.value.code == "account_deleted"
