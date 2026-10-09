"""The body-size and rate-limit middleware.

Both guards key off attacker-controlled input (a Content-Length header, and for anonymous traffic a
forwarded address the deployment cannot pin), and the rate-limit table is held in process memory, so
its bound, its eviction, and what it uses as a bucket are worth pinning down. The limit constants
are patched down here; the production values are not what is under test.
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
    assert list(windows) == ["address:unknown"]


async def test_requests_older_than_the_window_are_already_forgiven(windows: Any) -> None:
    call_next = Passthrough()
    stale = time.monotonic() - 61
    windows["address:203.0.113.1"] = deque([stale, stale, stale, stale])
    response = await rate_limit.apply_limits(make_request(), call_next)  # type: ignore[arg-type]
    assert response.status_code == 200
    assert len(windows["address:203.0.113.1"]) == 1


async def test_the_table_holds_its_bound_by_dropping_the_least_recently_seen_client(
    windows: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_TRACKED_CLIENTS", 2)
    call_next = Passthrough()
    await rate_limit.apply_limits(make_request("203.0.113.1"), call_next)  # type: ignore[arg-type]
    await rate_limit.apply_limits(make_request("203.0.113.2"), call_next)  # type: ignore[arg-type]
    assert list(windows) == ["address:203.0.113.1", "address:203.0.113.2"]

    # Seeing 203.0.113.1 again makes it the newest, so the flood evicts 203.0.113.2 instead.
    await rate_limit.apply_limits(make_request("203.0.113.1"), call_next)  # type: ignore[arg-type]
    await rate_limit.apply_limits(make_request("198.51.100.9"), call_next)  # type: ignore[arg-type]
    assert list(windows) == ["address:203.0.113.1", "address:198.51.100.9"]


async def test_a_flood_of_new_addresses_cannot_grow_the_table_without_bound(
    windows: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_TRACKED_CLIENTS", 2)
    call_next = Passthrough()
    for last_octet in range(200):
        await rate_limit.apply_limits(make_request(f"203.0.113.{last_octet}"), call_next)  # type: ignore[arg-type]
    assert len(windows) == 2
    assert "address:203.0.113.199" in windows


async def test_a_bearer_token_gets_one_bucket_and_the_address_stops_mattering(windows: Any) -> None:
    """A forwarded address is not dependable on Heroku, so a credential keys its own bucket."""
    call_next = Passthrough()
    token = {"authorization": "Bearer synthetic-token"}
    for _ in range(3):
        assert (await rate_limit.apply_limits(make_request("203.0.113.1", token), call_next)).status_code == 200  # type: ignore[arg-type]
    assert (await rate_limit.apply_limits(make_request("198.51.100.2", token), call_next)).status_code == 429  # type: ignore[arg-type]


async def test_two_credentials_never_share_a_bucket(windows: Any) -> None:
    """Exhausting one caller must not silence the next one behind the same router address."""
    call_next = Passthrough()
    statuses = []
    for _ in range(4):
        response = await rate_limit.apply_limits(
            make_request("203.0.113.1", {"authorization": "Bearer token-a"}), call_next
        )  # type: ignore[arg-type]
        statuses.append(response.status_code)
    assert statuses == [200, 200, 200, 429]
    assert (
        await rate_limit.apply_limits(make_request("203.0.113.1", {"authorization": "Bearer token-b"}), call_next)  # type: ignore[arg-type]
    ).status_code == 200
    assert len(windows) == 2


async def test_the_table_holds_a_digest_and_never_the_credential(windows: Any) -> None:
    token = "eyJhbGciOi synthetic-signin-token-not-a-real-credential"
    await rate_limit.apply_limits(make_request("203.0.113.1", {"authorization": f"Bearer {token}"}), Passthrough())  # type: ignore[arg-type]
    assert len(windows) == 1
    key = next(iter(windows))
    assert key.startswith("credential:")
    assert token not in key
    assert token not in "".join(windows)


async def test_a_non_bearer_authorization_header_falls_back_to_the_address(windows: Any) -> None:
    await rate_limit.apply_limits(
        make_request("203.0.113.7", {"authorization": "Basic c3ludGhldGljCg=="}), Passthrough()
    )  # type: ignore[arg-type]
    assert list(windows) == ["address:203.0.113.7"]


async def test_the_response_carries_the_headers_helmet_used_to_set(windows: Any) -> None:
    response = await rate_limit.apply_limits(make_request(), Passthrough())  # type: ignore[arg-type]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-dns-prefetch-control"] == "off"
