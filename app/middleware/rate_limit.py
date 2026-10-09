"""Per-process request rate limiting and standard response security headers.

The window table is process memory, so a limit applies to one process: running N web dynos raises
the effective ceiling to N times `RATE_LIMIT_PER_MINUTE` for a caller that can spread its requests
across them. That is accepted while the deployment is a single dyno, and it is the honest scope of
the guard -- it bounds a caller hammering this process, not a fleet. Making it a global limit needs
shared state (Postgres or Redis), not a second in-memory table.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import Response

from app.errors import ApiError
from app.middleware.body_limit import MAX_BODY_BYTES, has_oversized_declared_body, is_streamed_upload

RATE_LIMIT_PER_MINUTE = 240
RATE_LIMIT_WINDOW_SECONDS = 60
# One window per client, so the table itself needs a ceiling.
RATE_LIMIT_TRACKED_CLIENTS = 4096


class _WindowTable(OrderedDict[str, deque[float]]):
    """Sliding request windows, ordered least-recently-seen first.

    Re-inserting a client on every request puts the active ones at the back, so hitting the ceiling
    evicts the quietest clients and the cost stays O(1). A periodic full sweep would instead be O(n)
    on every request once a caller with forgeable identity had filled the table.
    """

    def record(self, bucket: str, now: float) -> bool:
        """Count this request; report whether the client is still inside its window limit."""
        window = self.pop(bucket, None) or deque()
        while window and now - window[0] >= RATE_LIMIT_WINDOW_SECONDS:
            window.popleft()
        self[bucket] = window
        if len(window) >= RATE_LIMIT_PER_MINUTE:
            return False
        window.append(now)
        while len(self) > RATE_LIMIT_TRACKED_CLIENTS:
            self.popitem(last=False)
        return True


_windows = _WindowTable()


def _bucket(request: Request) -> str:
    """Key authenticated traffic on its credential and anonymous traffic on its address.

    Heroku's common runtime cannot pin the proxy that sets `X-Forwarded-For` and documents that
    header as untrusted, so an address is not a dependable identity for a caller who already holds
    a token. A digest of that token is: minting another bucket means obtaining another credential,
    which goes through the anonymous sign-in endpoints and the provider's own throttles. The token
    itself is never stored, only its digest.

    Anonymous traffic keeps the address bucket, which a forged forwarded header can evade -- it is
    a floor, not a guarantee. Sign-in and sign-up abuse is bounded by Supabase Auth's own rate
    limits and the email provider's send quota, which is where the real protection for those
    unauthenticated endpoints lives.
    """
    scheme, _, credential = request.headers.get("authorization", "").partition(" ")
    token = credential.strip()
    if scheme.lower() == "bearer" and token:
        return "credential:" + hashlib.sha256(token.encode()).hexdigest()[:32]
    return "address:" + (request.client.host if request.client else "unknown")


def _add_security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-DNS-Prefetch-Control", "off")
    return response


async def apply_limits(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Apply the early declared-size check, per-client rate limit, and security headers."""
    if not is_streamed_upload(request.method, request.url.path) and has_oversized_declared_body(
        request.headers, MAX_BODY_BYTES
    ):
        return _add_security_headers(ApiError(413, "payload_too_large", "The request body is too large.").to_response())

    if not _windows.record(_bucket(request), time.monotonic()):
        return _add_security_headers(
            ApiError(429, "rate_limited", "Too many requests. Please slow down.").to_response()
        )
    response = await call_next(request)
    return _add_security_headers(response)
