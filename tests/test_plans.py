import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.auth import Principal
from app.domain.plans import FREE_PLAN, PAID_PLAN, get_storage_plan
from app.errors import ApiError
from app.routes import accounts, uploads

USER_ID = "00000000-0000-4000-8000-000000000002"
ASSET_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def test_plan_caps_are_server_owned():
    assert FREE_PLAN.limit_bytes == 200_000_000
    assert PAID_PLAN.limit_bytes == 1_000_000_000
    with pytest.raises(ValueError):
        get_storage_plan("unlimited")


def test_storage_usage_is_reported_without_a_negative_remainder():
    assert accounts.Plan.from_usage(get_storage_plan("free"), 25_000_000).model_dump() == {
        "id": "free",
        "name": "Free",
        "storageLimitBytes": 200_000_000,
        "storageUsedBytes": 25_000_000,
        "storageRemainingBytes": 175_000_000,
    }
    assert accounts.Plan.from_usage(PAID_PLAN, 1_100_000_000).storageRemainingBytes == 0


async def test_plan_endpoint_returns_owned_storage_usage(monkeypatch):
    lookup = AsyncMock(return_value={"storage_plan": "paid", "storage_used_bytes": 10_000_000})
    monkeypatch.setattr(accounts, "fetchrow", lookup)
    response = await accounts.get_plan(Principal(id=USER_ID, subject="test"))
    assert lookup.call_args.args[1] == uuid.UUID(USER_ID)
    assert b'"id":"paid"' in response.body
    assert b'"storageUsedBytes":10000000' in response.body
    assert "a.user_id=u.id" in lookup.call_args.args[0]


class FakeConnection:
    def __init__(self, used_bytes: int, plan: str = "free") -> None:
        self.used_bytes = used_bytes
        self.plan = plan
        self.calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query: str, *args):
        self.calls.append((query, args))
        if "SELECT storage_plan" in query:
            return {"storage_plan": self.plan}
        return {"id": ASSET_ID}

    async def fetchval(self, query: str, *args):
        self.calls.append((query, args))
        return self.used_bytes


def upload_request(payload: dict) -> Request:
    import json

    body = json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "headers": [(b"content-type", b"application/json")]}, receive)


async def call_create_upload(monkeypatch, connection: FakeConnection, byte_size: int):
    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(uploads, "transaction", transaction)
    monkeypatch.setattr(uploads.storage, "new_object_key", lambda user, name: f"{user}/{name}")
    monkeypatch.setattr(uploads, "get_config", lambda: SimpleNamespace(MAX_UPLOAD_BYTES=52_428_800))
    return await uploads.create_upload(
        upload_request({"filename": "synthetic.bin", "mimeType": "application/octet-stream", "byteSize": byte_size}),
        Principal(id=USER_ID, subject="test"),
    )


async def test_upload_allocation_serializes_quota_check_and_reserves_bytes(monkeypatch):
    connection = FakeConnection(used_bytes=199_000_000)
    response = await call_create_upload(monkeypatch, connection, byte_size=1_000_000)
    assert response.status_code == 201
    assert "FOR UPDATE" in connection.calls[0][0]
    assert "pending_upload" in connection.calls[1][0]
    assert "INSERT INTO assets" in connection.calls[2][0]


async def test_free_upload_exceeding_storage_limit_is_rejected_before_insert(monkeypatch):
    connection = FakeConnection(used_bytes=199_000_001)
    with pytest.raises(ApiError) as error:
        await call_create_upload(monkeypatch, connection, byte_size=1_000_000)
    assert error.value.status_code == 413
    assert error.value.code == "storage_quota_exceeded"
    assert len(connection.calls) == 2


async def test_paid_plan_uses_its_larger_limit(monkeypatch):
    connection = FakeConnection(used_bytes=999_000_000, plan="paid")
    response = await call_create_upload(monkeypatch, connection, byte_size=1_000_000)
    assert response.status_code == 201
