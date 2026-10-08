import io
import uuid
from unittest.mock import AsyncMock

import pytest
from botocore.response import StreamingBody
from starlette.requests import Request

from app.auth import Principal
from app.errors import ApiError
from app.media import parse_byte_range
from app.routes import media

USER = uuid.UUID("00000000-0000-4000-8000-000000000002")
ASSET = uuid.UUID("00000000-0000-4000-8000-000000000001")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("bytes=0-2", (0, 2)), ("bytes=3-", (3, 4)), ("bytes=-2", (3, 4)), ("bytes=0-99", (0, 4)), ("bytes=-99", (0, 4))],
)
def test_ranges(value, expected):
    result = parse_byte_range(value, 5)
    assert (result.start, result.end) == expected


@pytest.mark.parametrize("value", ["bytes=-0", "bytes=5-", "bytes=3-2", "bytes=0-1,3-4", "garbage", "bytes=-"])
def test_invalid_ranges(value):
    with pytest.raises(ValueError):
        parse_byte_range(value, 5)


def request(value=None):
    return Request({"type": "http", "method": "GET", "headers": [(b"range", value.encode())] if value else []})


@pytest.fixture
def delivery(monkeypatch):
    lookup = AsyncMock(return_value={"object_key": "private/synthetic", "mime_type": "audio/mpeg"})
    head = AsyncMock(return_value=5)
    body = StreamingBody(io.BytesIO(b"hello"), 5)
    opened = AsyncMock(return_value=(body, 5))
    monkeypatch.setattr(media, "fetchrow", lookup)
    monkeypatch.setattr(media.storage, "head_object_size", head)
    monkeypatch.setattr(media.storage, "open_object_stream", opened)
    return lookup, head, opened, body


async def test_media_streams_and_closes_private_object(delivery):
    lookup, _, _, body = delivery
    response = await media.asset_content(ASSET, request(), Principal(id=str(USER), subject="synthetic"))
    assert response.status_code == 200
    assert response.headers["content-length"] == "5"
    assert b"".join([chunk async for chunk in response.body_iterator]) == b"hello"
    assert body._raw_stream.closed
    assert lookup.call_args.args[1:] == (ASSET, USER)
    assert "m.deleted_at IS NULL" in lookup.call_args.args[0]


async def test_unowned_asset_never_opens_storage(delivery):
    lookup, head, opened, _ = delivery
    lookup.return_value = None
    with pytest.raises(ApiError) as error:
        await media.asset_content(ASSET, request(), Principal(id=str(USER), subject="synthetic"))
    assert error.value.status_code == 404
    head.assert_not_awaited()
    opened.assert_not_awaited()


async def test_media_range_returns_exact_requested_bytes(delivery):
    _, _, opened, _ = delivery
    opened.return_value = (StreamingBody(io.BytesIO(b"ell"), 3), 3)
    response = await media.asset_content(ASSET, request("bytes=1-3"), Principal(id=str(USER), subject="synthetic"))
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 1-3/5"
    assert b"".join([chunk async for chunk in response.body_iterator]) == b"ell"
    assert opened.call_args.args[1] == "bytes=1-3"


async def test_unsatisfiable_range_does_not_open_storage(delivery):
    response = await media.asset_content(ASSET, request("bytes=9-"), Principal(id=str(USER), subject="synthetic"))
    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */5"
    delivery[2].assert_not_awaited()


async def test_bad_storage_length_closes_before_returning_failure(delivery):
    delivery[2].return_value = (delivery[3], 4)
    with pytest.raises(ApiError) as error:
        await media.asset_content(ASSET, request(), Principal(id=str(USER), subject="synthetic"))
    assert error.value.status_code == 502
    assert delivery[3]._raw_stream.closed


async def test_disconnected_reader_closes_provider_stream(delivery):
    response = await media.asset_content(ASSET, request(), Principal(id=str(USER), subject="synthetic"))
    assert await anext(response.body_iterator) == b"hello"
    await response.body_iterator.aclose()
    assert delivery[3]._raw_stream.closed


async def test_missing_authentication_cannot_reach_storage(delivery):
    import httpx
    from fastapi import FastAPI

    application = FastAPI()
    application.include_router(media.router, prefix="/v1")

    @application.exception_handler(ApiError)
    async def handle_error(request, error):
        return error.to_response()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="https://api.example.test"
    ) as client:
        response = await client.get(f"/v1/assets/{ASSET}/content")
    assert response.status_code == 401
    delivery[0].assert_not_awaited()
    delivery[1].assert_not_awaited()
    delivery[2].assert_not_awaited()
