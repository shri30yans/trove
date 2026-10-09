"""The process lifecycle: what startup owns, and what teardown must still do when it fails.

Two invariants the previous code got wrong, held here: a boot that fails partway through releases
everything that already opened, and one resource refusing to close cannot strand the rest.
Nothing in this file touches a database or a provider -- the steps are recorded, not executed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

import app.main as main

STEPS = ("deletion worker", "memory queue", "embedding client", "database pool")


@asynccontextmanager
async def _no_mcp_sessions() -> AsyncIterator[None]:
    yield


def _fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    fail_to_start: str | None = None,
    fail_to_release: str | None = None,
) -> None:
    """Replace each lifecycle step with a record of itself.

    `fail_to_start` and `fail_to_release` name one step that raises instead, which is how the two
    partial-failure paths are exercised.
    """

    async def release(name: str) -> None:
        if name == fail_to_release:
            raise RuntimeError(f"{name} could not release")
        events.append(f"release:{name}")

    def begin(name: str) -> None:
        events.append(f"start:{name}")
        if name == fail_to_start:
            raise RuntimeError(f"{name} could not start")

    async def ok(*_args: Any, **_kwargs: Any) -> None:
        return None

    workers = ((main.memory_queue, "memory queue"), (main.account_deletion_worker, "deletion worker"))
    for worker, name in workers:
        monkeypatch.setattr(worker, "start", lambda name=name: begin(name))
        monkeypatch.setattr(worker, "stop", lambda name=name: release(name))

    monkeypatch.setattr(main.db, "open_pool", ok)
    monkeypatch.setattr(main.db, "fetchval", ok)
    monkeypatch.setattr(main.db, "close_pool", lambda: release("database pool"))
    monkeypatch.setattr(main.embeddings, "stop", lambda: release("embedding client"))
    monkeypatch.setattr(main, "_check_storage", ok)
    monkeypatch.setattr(main.mcp_server.session_manager, "run", _no_mcp_sessions)
    monkeypatch.setattr(main, "_configure_logging", lambda: events.append("logging"))


async def test_startup_opens_the_runtime_and_shutdown_releases_all_of_it(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _fake_runtime(monkeypatch, events)

    async with main.lifespan(main.app):
        assert events == ["logging", "start:memory queue", "start:deletion worker"]

    assert events[3:] == [f"release:{name}" for name in STEPS]


async def test_a_boot_that_fails_after_the_queue_started_still_releases_the_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deletion worker starts last, so a failure there used to leave the queue running."""
    events: list[str] = []
    _fake_runtime(monkeypatch, events, fail_to_start="deletion worker")

    with pytest.raises(RuntimeError, match="deletion worker could not start"):
        async with main.lifespan(main.app):
            pass

    assert "start:memory queue" in events
    assert events[-4:] == [f"release:{name}" for name in STEPS]


async def test_one_resource_refusing_to_close_does_not_strand_the_others(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    events: list[str] = []
    _fake_runtime(monkeypatch, events, fail_to_release="database pool")

    async with main.lifespan(main.app):
        pass

    assert "release:embedding client" in events
    assert "database pool could not release" in caplog.text
