import uuid
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.auth import Principal
from app.errors import ApiError
from app.routes import memories

USER = uuid.UUID("00000000-0000-4000-8000-000000000001")


async def test_memory_tag_suggestions_are_scoped_to_owner_and_search_prefix(monkeypatch):
    fetch = AsyncMock(return_value=[{"tag": "reading", "memory_count": 3}])
    monkeypatch.setattr(memories, "fetch", fetch)
    request = Request({"type": "http", "query_string": b"q=Read"})

    result = await memories.list_memory_tags(request, Principal(id=str(USER), subject="synthetic"))

    assert result.body == b'{"tags":[{"tag":"reading","memoryCount":3}]}'
    assert fetch.await_args.args[1:] == (USER, "read")
    assert "WHERE user_id=$1" in fetch.await_args.args[0]
    assert "LIMIT 50" in fetch.await_args.args[0]


async def test_memory_tag_suggestion_query_limit_is_validated(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(memories, "fetch", fetch)
    request = Request({"type": "http", "query_string": b"q=" + b"a" * 41})

    with pytest.raises(ApiError) as error:
        await memories.list_memory_tags(request, Principal(id=str(USER), subject="synthetic"))

    assert error.value.code == "invalid_tag"
    fetch.assert_not_awaited()
