"""Per-process request rate limiting and standard response security headers."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import Response

from app.errors import ApiError
from app.middleware.body_limit import MAX_BODY_BYTES, has_oversized_declared_body, is_streamed_upload

RATE_LIMIT_PER_MINUTE = 240
RATE_LIMIT_WINDOW_SECONDS = 60
# One deque per client address, so the table itself needs a ceiling; a sweep drops the quiet ones.
RATE_LIMIT_TRACKED_CLIENTS = 4096

_windows: dict[str, deque[float]] = defaultdict(deque)


def _add_security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-DNS-Prefetch-Control", "off")
    return response


def _forget_quiet_clients(now: float) -> None:
    """Drop clients quiet for a whole window to bound the in-memory table."""
    quiet_clients = [
        client for client, window in _windows.items() if not window or now - window[-1] >= RATE_LIMIT_WINDOW_SECONDS
    ]
    for client in quiet_clients:
        del _windows[client]


async def apply_limits(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Apply the early declared-size check, per-client rate limit, and security headers."""
    if not is_streamed_upload(request.method, request.url.path) and has_oversized_declared_body(
        request.headers, MAX_BODY_BYTES
    ):
        return _add_security_headers(ApiError(413, "payload_too_large", "The request body is too large.").to_response())

    now = time.monotonic()
    client = request.client.host if request.client else "unknown"
    window = _windows[client]
    while window and now - window[0] >= RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MINUTE:
        return _add_security_headers(
            ApiError(429, "rate_limited", "Too many requests. Please slow down.").to_response()
        )
    window.append(now)
    if len(_windows) > RATE_LIMIT_TRACKED_CLIENTS:
        _forget_quiet_clients(now)

    response = await call_next(request)
    return _add_security_headers(response)
