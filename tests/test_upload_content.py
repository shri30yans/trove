from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app import upload_transfer
from app.auth import Principal
from app.errors import ApiError
from app.routes import uploads

ASSET_ID = "00000000-0000-4000-8000-000000000001"
USER_ID = "00000000-0000-4000-8000-000000000002"


def request_with_body(body: bytes) -> Request:
    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "PUT", "headers": []}, receive)


@pytest.fixture
def upload(monkeypatch):
    row = {
        "object_key": "owner/file",
        "byte_size": 5,
        "mime_type": "text/plain",
        "status": "pending_upload",
        "storage_plan": "free",
    }
    lookup = AsyncMock(return_value=row)
    release = AsyncMock()
    # The route answers with `execute` and the transport releases the reservation with its own copy of
    # the pooled helper, so one mock has to stand in for both.
    monkeypatch.setattr(uploads, "execute", release)
    monkeypatch.setattr(upload_transfer, "execute", release)
    stored = []

    async def write(path, key, mime):
        stored.append((Path(path).read_bytes(), key, mime))

    monkeypatch.setattr(uploads, "fetchrow", lookup)
    monkeypatch.setattr(uploads, "get_config", lambda: SimpleNamespace(MAX_UPLOAD_BYTES=1024))
    monkeypatch.setattr(uploads.storage, "upload_file", write)
    return row, lookup, stored, release


async def send(body):
    return await uploads.upload_content(
        ASSET_ID, request_with_body(body), Principal(id=USER_ID, subject="test", embeddings_enabled=False)
    )


async def test_upload_streams_exact_content_and_scopes_lookup_to_owner(upload):
    _, lookup, stored, _ = upload
    response = await send(b"hello")
    assert response.status_code == 200
    assert stored == [(b"hello", "owner/file", "text/plain")]
    assert str(lookup.call_args.args[2]) == USER_ID
    assert "user_id=$2" in lookup.call_args.args[0]


@pytest.mark.parametrize(("body", "status"), [(b"toolong", 413), (b"hi", 422)])
async def test_invalid_size_never_reaches_storage(upload, body, status):
    with pytest.raises(ApiError) as error:
        await send(body)
    assert error.value.status_code == status
    assert upload[2] == []
    upload[3].assert_awaited_once()


async def test_failed_upload_allocation_cannot_be_reused(upload):
    upload[0]["status"] = "failed"
    with pytest.raises(ApiError) as error:
        await send(b"hello")
    assert error.value.status_code == 409
    assert error.value.code == "upload_invalidated"
    assert upload[2] == []


async def test_upload_cannot_overwrite_completed_asset(upload):
    upload[0]["status"] = "attached"
    with pytest.raises(ApiError) as error:
        await send(b"hello")
    assert error.value.status_code == 409
    assert upload[2] == []


async def test_unknown_or_other_account_asset_is_not_found(upload):
    upload[1].return_value = None
    with pytest.raises(ApiError) as error:
        await send(b"hello")
    assert error.value.status_code == 404
    assert upload[2] == []


async def test_storage_failure_is_reported_as_retryable_gateway_error(upload, monkeypatch):
    monkeypatch.setattr(uploads.storage, "upload_file", AsyncMock(side_effect=OSError("connection failed")))
    with pytest.raises(ApiError) as error:
        await send(b"hello")
    assert error.value.status_code == 502


async def test_rejected_storage_credentials_are_visible_without_exposing_secrets(upload, monkeypatch):
    from botocore.exceptions import ClientError

    failure = ClientError(
        {"Error": {"Code": "InvalidAccessKeyId"}, "ResponseMetadata": {"HTTPStatusCode": 403}}, "PutObject"
    )
    monkeypatch.setattr(uploads.storage, "upload_file", AsyncMock(side_effect=failure))
    with pytest.raises(ApiError) as error:
        await send(b"hello")
    assert error.value.status_code == 503
    assert "storage credentials" in error.value.message


@pytest.mark.parametrize("status", ["pending_upload", "uploaded", "attached"])
async def test_completion_returns_verified_size_on_first_call_and_retry(upload, monkeypatch, status):
    import json

    upload[0]["status"] = status
    head = AsyncMock(return_value=5)
    update = AsyncMock()
    monkeypatch.setattr(uploads.storage, "head_object_size", head)
    monkeypatch.setattr(uploads, "execute", update)
    response = await uploads.complete_upload(ASSET_ID, Principal(id=USER_ID, subject="test", embeddings_enabled=False))
    assert json.loads(response.body)["byteSize"] == 5
    assert head.await_count == (1 if status == "pending_upload" else 0)
    assert update.await_count == (1 if status == "pending_upload" else 0)


@pytest.mark.parametrize("size", [None, 0, -1, "5", True])
async def test_completion_rejects_invalid_persisted_size(upload, monkeypatch, size):
    upload[0].update(status="uploaded", byte_size=size)
    head = AsyncMock()
    monkeypatch.setattr(uploads.storage, "head_object_size", head)
    with pytest.raises(ApiError) as error:
        await uploads.complete_upload(ASSET_ID, Principal(id=USER_ID, subject="test", embeddings_enabled=False))
    assert error.value.code == "invalid_upload_record"
    head.assert_not_awaited()


async def test_completion_mismatch_never_confirms_upload(upload, monkeypatch):
    update = AsyncMock()
    monkeypatch.setattr(uploads, "execute", update)
    monkeypatch.setattr(uploads.storage, "head_object_size", AsyncMock(return_value=4))
    with pytest.raises(ApiError) as error:
        await uploads.complete_upload(ASSET_ID, Principal(id=USER_ID, subject="test", embeddings_enabled=False))
    assert error.value.code == "upload_size_mismatch"
    update.assert_not_awaited()


@pytest.mark.parametrize("stage", ["transfer", "completion"])
async def test_storage_connection_failure_is_consistent_across_upload_stages(upload, monkeypatch, stage):
    operation = "upload_file" if stage == "transfer" else "head_object_size"
    monkeypatch.setattr(uploads.storage, operation, AsyncMock(side_effect=OSError("connection failed")))
    operation_call = (
        send(b"hello")
        if stage == "transfer"
        else uploads.complete_upload(ASSET_ID, Principal(id=USER_ID, subject="test", embeddings_enabled=False))
    )
    with pytest.raises(ApiError) as error:
        await operation_call
    assert error.value.status_code == 502
    assert error.value.code == "storage_unavailable"


async def test_storage_programming_error_is_not_classified_as_connection_failure(upload, monkeypatch):
    monkeypatch.setattr(uploads.storage, "upload_file", AsyncMock(side_effect=TypeError("invalid argument")))
    with pytest.raises(TypeError):
        await send(b"hello")
