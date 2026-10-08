"""The body-size and rate-limit middleware.

Both guards key off attacker-controlled input (a Content-Length header, the source address), and the
rate-limit table is held in process memory, so its bound and its eviction are worth pinning down.
The limit constants are patched down here; the production values are not what is under test.
"""

from __future__ import annotations

import time
from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Response
from starlette.requests import Request

from app.middleware import rate_limit


class Passthrough:
    """The call_next the middleware is handed: counts how often the request was allowed through."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, _request: Request) -> Response:
        self.calls += 1
        return Response(status_code=200)


def make_request(host: str = "203.0.113.1", headers: dict[str, str] | None = None) -> Any:
    """A request with the ASGI request attributes the middleware reads."""
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=host) if host else None,
        method="POST",
        url=SimpleNamespace(path="/test"),
    )


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> Any:
    rate_limit._windows.clear()
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_PER_MINUTE", 3)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_TRACKED_CLIENTS", 4096)
    return rate_limit._windows


async def test_a_declared_body_over_the_limit_is_refused_before_it_is_read(windows: Any) -> None:
    call_next = Passthrough()
    request = make_request(headers={"content-length": str(rate_limit.MAX_BODY_BYTES + 1)})
    response = await rate_limit.apply_limits(request, call_next)  # type: ignore[arg-type]
    assert response.status_code == 413
    assert call_next.calls == 0


async def test_a_lying_content_length_does_not_shorten_the_body(windows: Any) -> None:
    call_next = Passthrough()
    response = await rate_limit.apply_limits(make_request(headers={"content-length": "abc"}), call_next)  # type: ignore[arg-type]
    assert response.status_code == 200
    assert call_next.calls == 1


async def test_a_client_over_the_limit_is_told_to_slow_down(windows: Any) -> None:
    call_next = Passthrough()
    request = make_request()
    for _ in range(3):
        assert (await rate_limit.apply_limits(request, call_next)).status_code == 200  # type: ignore[arg-type]
    response = await rate_limit.apply_limits(request, call_next)  # type: ignore[arg-type]
    assert response.status_code == 429
    assert call_next.calls == 3


async def test_one_client_cannot_spend_another_s_budget(windows: Any) -> None:
    call_next = Passthrough()
    for _ in range(3):
        await rate_limit.apply_limits(make_request("203.0.113.1"), call_next)  # type: ignore[arg-type]
    assert (await rate_limit.apply_limits(make_request("203.0.113.1"), call_next)).status_code == 429  # type: ignore[arg-type]
    assert (await rate_limit.apply_limits(make_request("198.51.100.2"), call_next)).status_code == 200  # type: ignore[arg-type]


async def test_an_absent_peer_address_gets_its_own_bucket(windows: Any) -> None:
    call_next = Passthrough()
    for _ in range(4):
        assert (await rate_limit.apply_limits(make_request(""), call_next)).status_code in (200, 429)  # type: ignore[arg-type]
    assert list(windows) == ["unknown"]


async def test_requests_older_than_the_window_are_already_forgiven(windows: Any) -> None:
    call_next = Passthrough()
    stale = time.monotonic() - 61
    windows["203.0.113.1"] = deque([stale, stale, stale, stale])
    response = await rate_limit.apply_limits(make_request(), call_next)  # type: ignore[arg-type]
    assert response.status_code == 200
    assert len(windows["203.0.113.1"]) == 1


async def test_quiet_clients_are_dropped_from_the_table(windows: Any) -> None:
    now = time.monotonic()
    windows["quiet"] = deque([now - 61])
    windows["idle"] = deque()
    windows["active"] = deque([now - 1])
    rate_limit._forget_quiet_clients(now)
    assert list(windows) == ["active"]


async def test_a_flood_of_new_addresses_cannot_grow_the_table_without_bound(
    windows: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_TRACKED_CLIENTS", 2)
    call_next = Passthrough()
    now = time.monotonic()
    windows["old-1"] = deque([now - 61])
    windows["old-2"] = deque([now - 61])
    await rate_limit.apply_limits(make_request("203.0.113.9"), call_next)  # type: ignore[arg-type]
    assert "old-1" not in windows
    assert "old-2" not in windows
    assert "203.0.113.9" in windows


async def test_the_response_carries_the_headers_helmet_used_to_set(windows: Any) -> None:
    response = await rate_limit.apply_limits(make_request(), Passthrough())  # type: ignore[arg-type]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-dns-prefetch-control"] == "off"
