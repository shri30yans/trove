"""The Cloud screen's server-owned truth: whole-library processing counts."""

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.auth import Principal
from app.routes import accounts

USER_ID = "00000000-0000-4000-8000-000000000002"


async def test_processing_summary_counts_every_live_save(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup = AsyncMock(
        return_value=[
            {"status": "ready", "memory_count": 9},
            {"status": "failed", "memory_count": 2},
        ]
    )
    monkeypatch.setattr(accounts, "fetch", lookup)
    response = await accounts.processing_summary(Principal(id=USER_ID, subject="test"))

    assert lookup.call_args.args[1] == uuid.UUID(USER_ID)
    sql = lookup.call_args.args[0]
    assert "deleted_at IS NULL" in sql
    assert "GROUP BY status" in sql
    assert json.loads(response.body)["processing"] == {
        "queued": 0,
        "processing": 0,
        "ready": 9,
        "failed": 2,
        "total": 11,
    }


async def test_an_empty_library_still_reports_zeroes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(accounts, "fetch", AsyncMock(return_value=[]))
    response = await accounts.processing_summary(Principal(id=USER_ID, subject="test"))
    assert json.loads(response.body)["processing"] == {
        "queued": 0,
        "processing": 0,
        "ready": 0,
        "failed": 0,
        "total": 0,
    }
