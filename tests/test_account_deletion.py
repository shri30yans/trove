"""Deletion scheduling and cross-provider cleanup use synthetic account data."""

from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import account_deletion
from app.auth import Principal

SUBJECT = str(uuid.UUID(int=123))
USER_ID = str(uuid.UUID(int=456))
PRINCIPAL = Principal(id=USER_ID, subject=SUBJECT)


@pytest.mark.asyncio
async def test_deletion_request_schedules_exactly_seven_days(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_at = dt.datetime(2026, 10, 8, tzinfo=dt.UTC)
    delete_after = requested_at + dt.timedelta(days=7)
    monkeypatch.setattr(account_deletion, "fetchval", AsyncMock(return_value=None))
    lookup = AsyncMock(
        return_value={"requested_at": requested_at, "delete_after": delete_after, "deletion_cancellable": True}
    )
    monkeypatch.setattr(account_deletion, "fetchrow", lookup)

    result = await account_deletion.request_account_deletion(PRINCIPAL)

    assert result == {"requestedAt": requested_at, "deleteAfter": delete_after, "deletionCancellable": True}
    assert "interval '7 days'" in lookup.call_args.args[0]
    assert lookup.call_args.args[1:] == (SUBJECT, uuid.UUID(USER_ID))


@pytest.mark.asyncio
async def test_cancel_removes_only_a_request_before_its_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup = AsyncMock(return_value={"auth_subject": SUBJECT})
    monkeypatch.setattr(account_deletion, "fetchrow", lookup)

    await account_deletion.cancel_account_deletion(SUBJECT)

    assert "delete_after > now()" in lookup.call_args.args[0]
    assert lookup.call_args.args[1] == SUBJECT


@pytest.mark.asyncio
async def test_status_reports_that_an_expired_request_cannot_be_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    delete_after = dt.datetime(2026, 10, 8, tzinfo=dt.UTC)
    monkeypatch.setattr(
        account_deletion,
        "fetchrow",
        AsyncMock(
            return_value={
                "requested_at": delete_after - dt.timedelta(days=7),
                "delete_after": delete_after,
                "deletion_cancellable": False,
            }
        ),
    )

    status = await account_deletion.account_deletion_status(SUBJECT)

    assert status["deletionScheduled"] is True
    assert status["deletionCancellable"] is False


@pytest.mark.asyncio
async def test_due_deletion_removes_storage_database_auth_then_pending_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        account_deletion, "fetch", AsyncMock(return_value=[{"auth_subject": SUBJECT, "user_id": USER_ID}])
    )
    calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(sql: str, *args: object) -> None:
        calls.append(("execute", (sql, *args)))

    class Connection:
        async def execute(self, sql: str, *args: object) -> None:
            calls.append(("database", (sql, *args)))

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(account_deletion, "execute", execute)
    monkeypatch.setattr(account_deletion, "transaction", lambda: Transaction())
    delete_objects = AsyncMock()
    delete_auth_user = AsyncMock()
    monkeypatch.setattr(account_deletion.storage, "delete_user_objects", delete_objects)
    monkeypatch.setattr(account_deletion.supabase_auth, "delete_user", delete_auth_user)

    completed = await account_deletion.process_due_account_deletions()

    assert completed == 1
    delete_objects.assert_awaited_once_with(USER_ID)
    delete_auth_user.assert_awaited_once_with(SUBJECT)
    assert calls[0][0] == "execute"
    assert "deleted_auth_subjects" in str(calls[0][1][0])
    assert calls[1][0] == "database"
    assert "DELETE FROM app_users" in str(calls[1][1][0])
    assert calls[2][0] == "execute"
    assert "DELETE FROM account_deletion_requests" in str(calls[2][1][0])


@pytest.mark.asyncio
async def test_failed_storage_cleanup_keeps_the_deletion_request_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        account_deletion, "fetch", AsyncMock(return_value=[{"auth_subject": SUBJECT, "user_id": USER_ID}])
    )
    monkeypatch.setattr(account_deletion, "execute", AsyncMock())
    monkeypatch.setattr(
        account_deletion,
        "storage",
        SimpleNamespace(delete_user_objects=AsyncMock(side_effect=OSError("synthetic storage outage"))),
    )
    delete_auth_user = AsyncMock()
    monkeypatch.setattr(account_deletion, "supabase_auth", SimpleNamespace(delete_user=delete_auth_user))

    completed = await account_deletion.process_due_account_deletions()

    assert completed == 0
    delete_auth_user.assert_not_awaited()
