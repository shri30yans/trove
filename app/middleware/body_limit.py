"""Bound incoming HTTP bodies, including requests sent with chunked transfer."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import ApiError

MAX_BODY_BYTES = 1_000_000
_UPLOAD_CONTENT_PATH = re.compile(r"/v1/uploads/[0-9a-fA-F-]{36}/content\Z")


def is_streamed_upload(method: str, path: str) -> bool:
    """File contents have their own streaming size limit in the authenticated upload handler."""
    return method == "PUT" and _UPLOAD_CONTENT_PATH.fullmatch(path) is not None


def has_oversized_declared_body(
    headers: Iterable[tuple[bytes, bytes]] | Mapping[str, str], max_body_bytes: int = MAX_BODY_BYTES
) -> bool:
    if isinstance(headers, Mapping):
        declared = headers.get("content-length", "").strip()
    else:
        declared = next(
            (value.decode("latin-1").strip() for name, value in headers if name.lower() == b"content-length"),
            "",
        )
    return declared.isdigit() and int(declared) > max_body_bytes


class RequestBodyLimitMiddleware:
    """Reject oversized bodies as they arrive, without trusting Content-Length."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if is_streamed_upload(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return

        if has_oversized_declared_body(scope["headers"], self.max_body_bytes):
            response = ApiError(413, "payload_too_large", "The request body is too large.").to_response()
            await response(scope, receive, send)
            return

        body = bytearray()
        pending_message: Message | None = None
        while True:
            message = await receive()
            if message["type"] != "http.request":
                pending_message = message
                break
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                response = ApiError(413, "payload_too_large", "The request body is too large.").to_response()
                await response(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                if pending_message is not None:
                    return pending_message
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)
