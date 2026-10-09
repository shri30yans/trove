import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.auth import Principal
from app.errors import ApiError
from app.routes import memory_lifecycle
from app.schemas import MoveMemoryRequest

USER = uuid.UUID("00000000-0000-4000-8000-000000000001")
MEMORY = uuid.UUID("00000000-0000-4000-8000-000000000002")
SOURCE = uuid.UUID("00000000-0000-4000-8000-000000000003")
TARGET = uuid.UUID("00000000-0000-4000-8000-000000000004")


def request():
    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps({"fromSpaceId": str(SOURCE), "toSpaceId": str(TARGET)}).encode(),
            "more_body": False,
        }

    return Request({"type": "http", "method": "POST", "headers": []}, receive)


@pytest.fixture
def connection(monkeypatch):
    connection = SimpleNamespace(
        fetchrow=AsyncMock(side_effect=[{"id": MEMORY}, {"memory_id": MEMORY}]),
        fetch=AsyncMock(return_value=[{"id": SOURCE}, {"id": TARGET}]),
        execute=AsyncMock(),
    )

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(memory_lifecycle, "transaction", transaction)
    monkeypatch.setattr(memory_lifecycle, "read_back", AsyncMock(return_value={"id": str(MEMORY)}))
    return connection


async def move():
    return await memory_lifecycle.move_memory(
        request(), str(MEMORY), Principal(id=str(USER), subject="synthetic", embeddings_enabled=False)
    )


async def test_move_locks_owned_memory_and_changes_only_selected_memberships(connection):
    response = await move()
    assert response.status_code == 200
    lookup, removed = connection.fetchrow.call_args_list
    assert "FOR UPDATE" in lookup.args[0]
    assert lookup.args[1:] == (MEMORY, USER)
    assert removed.args[1:] == (MEMORY, USER, SOURCE)
    assert "space_id=$3" in removed.args[0]
    assert connection.execute.call_args_list[0].args[1:] == (MEMORY, TARGET, USER)
    assert "FOR SHARE" in connection.fetch.call_args.args[0]


async def test_unowned_memory_is_rejected_before_membership_changes(connection):
    connection.fetchrow.side_effect = [None]
    with pytest.raises(ApiError) as error:
        await move()
    assert error.value.status_code == 404
    connection.fetch.assert_not_awaited()
    connection.execute.assert_not_awaited()


async def test_unowned_destination_is_rejected_before_removing_source(connection):
    connection.fetch.return_value = [{"id": SOURCE}]
    with pytest.raises(ApiError) as error:
        await move()
    assert error.value.status_code == 400
    assert connection.fetchrow.await_count == 1
    connection.execute.assert_not_awaited()


async def test_retry_accepts_existing_destination_without_replacing_other_memberships(connection):
    connection.fetchrow.side_effect = [{"id": MEMORY}, None, {"memory_id": MEMORY}]
    assert (await move()).status_code == 200
    assert connection.fetchrow.call_args_list[-1].args[1:] == (MEMORY, USER, TARGET)


async def test_missing_source_and_destination_reports_conflict(connection):
    connection.fetchrow.side_effect = [{"id": MEMORY}, None, None]
    with pytest.raises(ApiError) as error:
        await move()
    assert error.value.status_code == 409
    connection.execute.assert_not_awaited()


def test_move_rejects_same_space_and_unknown_writable_fields():
    with pytest.raises(ValidationError):
        MoveMemoryRequest(fromSpaceId=SOURCE, toSpaceId=SOURCE)
    with pytest.raises(ValidationError):
        MoveMemoryRequest.model_validate({"fromSpaceId": SOURCE, "toSpaceId": TARGET, "userId": USER})
