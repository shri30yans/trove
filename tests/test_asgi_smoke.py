"""The whole ASGI surface, exercised offline.

This is the check that the deployed route table, the auth gate, the middleware wiring and the
disabled developer endpoints are all still true, without a database, a bucket, or a provider: every
request goes to the ASGI app directly, so the lifespan never opens anything. A route that answers
something other than 401 to an anonymous caller is a hole, and the sweep over `PROTECTED_ROUTES`
is what notices.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.main import app
from app.middleware.body_limit import MAX_BODY_BYTES

FAKE_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "22222222-2222-2222-2222-222222222222"

# Every operation the API publishes. A route added or renamed here is a client-visible change.
ROUTE_TABLE = {
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/health/embeddings"),
    ("GET", "/oauth/consent"),
    ("POST", "/oauth/consent/decision"),
    ("POST", "/oauth/consent/login"),
    ("POST", "/v1/auth/sign-in"),
    ("POST", "/v1/auth/sign-up"),
    ("POST", "/v1/auth/refresh"),
    ("POST", "/v1/auth/sign-out"),
    ("POST", "/v1/auth/password-reset"),
    ("POST", "/v1/auth/resend-confirmation"),
    ("POST", "/v1/auth/confirm-email"),
    ("PUT", "/v1/auth/password"),
    ("DELETE", "/v1/auth/account"),
    ("GET", "/v1/auth/account/deletion"),
    ("POST", "/v1/auth/account/deletion/cancel"),
    ("GET", "/v1/me"),
    ("GET", "/v1/plan"),
    ("GET", "/v1/preferences"),
    ("PATCH", "/v1/preferences"),
    ("GET", "/v1/explore"),
    ("GET", "/v1/updates"),
    ("GET", "/v1/processing"),
    ("GET", "/v1/export/markdown"),
    ("GET", "/v1/search"),
    ("GET", "/v1/spaces"),
    ("POST", "/v1/spaces"),
    ("PATCH", "/v1/spaces/{space_id}"),
    ("DELETE", "/v1/spaces/{space_id}"),
    ("GET", "/v1/memories"),
    ("POST", "/v1/memories"),
    ("GET", "/v1/memories/{memory_id}"),
    ("PATCH", "/v1/memories/{memory_id}"),
    ("DELETE", "/v1/memories/{memory_id}"),
    ("GET", "/v1/memories/{memory_id}/preview"),
    ("POST", "/v1/memories/{memory_id}/move"),
    ("POST", "/v1/memories/{memory_id}/restore"),
    ("POST", "/v1/memories/{memory_id}/retry"),
    ("GET", "/v1/memories/{memory_id}/related"),
    ("PUT", "/v1/memories/{memory_id}/related/{related_id}/feedback"),
    ("GET", "/v1/assets/{asset_id}/content"),
    ("POST", "/v1/uploads"),
    ("PUT", "/v1/uploads/{asset_id}/content"),
    ("POST", "/v1/uploads/{asset_id}/complete"),
}

# Real URLs (not templates) that must refuse an anonymous caller. Write operations are deliberately
# absent: reaching their handler would need a database, and these are the read-shaped paths where
# authentication is decided first.
PROTECTED_ROUTES = [
    ("GET", "/v1/me"),
    ("GET", "/v1/preferences"),
    ("PATCH", "/v1/preferences"),
    ("GET", "/v1/explore"),
    ("GET", "/v1/updates"),
    ("GET", "/v1/spaces"),
    ("POST", "/v1/spaces"),
    ("PATCH", f"/v1/spaces/{FAKE_ID}"),
    ("DELETE", f"/v1/spaces/{FAKE_ID}"),
    ("POST", "/v1/uploads"),
    ("POST", f"/v1/uploads/{FAKE_ID}/complete"),
    ("POST", "/v1/memories"),
    ("GET", "/v1/memories"),
    ("GET", f"/v1/memories/{FAKE_ID}"),
    ("PATCH", f"/v1/memories/{FAKE_ID}"),
    ("DELETE", f"/v1/memories/{FAKE_ID}"),
    ("POST", f"/v1/memories/{FAKE_ID}/restore"),
    ("POST", f"/v1/memories/{FAKE_ID}/retry"),
    ("GET", "/v1/search?q=synthetic"),
    ("GET", f"/v1/memories/{FAKE_ID}/related"),
    ("PUT", f"/v1/memories/{FAKE_ID}/related/{OTHER_ID}/feedback"),
]


class AsgiResult:
    def __init__(self, status: int, headers: dict[bytes, bytes], body: str) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def json(self) -> Any:
        return json.loads(self.body)


async def asgi(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> AsgiResult:
    """Drive one request through the app without a server or a lifespan."""
    target, _, query = path.partition("?")
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": target,
        "raw_path": target.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [
            (b"host", b"api.local"),
            (b"content-type", b"application/json"),
            *[(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
        ],
        "client": ("203.0.113.1", 5555),
        "server": ("api.local", 80),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body or b"", "more_body": False}

    captured: dict[str, Any] = {"status": None, "headers": [], "body": b""}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    await app(scope, receive, send)
    assert captured["status"] is not None
    return AsgiResult(captured["status"], dict(captured["headers"]), captured["body"].decode())


def mounted_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        methods: set[str] = getattr(route, "methods", set())  # type: ignore[attr-defined]
        path: str = getattr(route, "path", "")  # type: ignore[attr-defined]
        routes.update((method, path) for method in methods - {"HEAD", "OPTIONS"})
    return routes


def test_the_route_table_is_the_published_surface() -> None:
    mounted = mounted_routes()
    assert mounted - ROUTE_TABLE == set()
    assert ROUTE_TABLE - mounted == set()


async def test_liveness_answers_without_any_dependency() -> None:
    result = await asgi("GET", "/health/live")
    assert result.status == 200
    assert result.json == {"status": "ok"}


async def test_readiness_reports_the_database_it_cannot_reach() -> None:
    result = await asgi("GET", "/health/ready")
    assert result.status == 503
    assert result.json == {"status": "not_ready"}


async def test_the_embedding_status_names_its_configuration_without_calling_the_provider() -> None:
    result = await asgi("GET", "/health/embeddings")
    assert result.status == 200
    status = result.json
    assert status["provider"] == "vertex_ai"
    assert status["dimensions"] == 768
    assert isinstance(status["ready"], bool)
    assert (status["configurationError"] is None) == status["ready"]


@pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
async def test_every_protected_operation_refuses_an_anonymous_caller(method: str, path: str) -> None:
    result = await asgi(method, path)
    assert result.status == 401
    assert result.json["error"]["code"] == "unauthorized"


async def test_a_response_carries_the_security_headers_and_no_server_identity() -> None:
    result = await asgi("GET", "/v1/me")
    headers = {name.lower(): value for name, value in result.headers.items()}
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"
    assert headers[b"referrer-policy"] == b"no-referrer"
    assert b"server" not in headers
    assert b"x-powered-by" not in headers


async def test_an_unknown_route_is_a_contract_shaped_404() -> None:
    result = await asgi("GET", "/v1/totally-unknown")
    assert result.status == 404
    assert result.json["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/auth/dev-token",
        "/docs",
        "/redoc",
        "/openapi.json",
    ],
)
async def test_developer_and_bypass_endpoints_are_not_served(path: str) -> None:
    result = await asgi("GET", path)
    assert result.status == 404


async def test_a_declared_body_over_the_limit_is_refused_at_the_edge() -> None:
    result = await asgi("POST", "/v1/memories", headers={"content-length": str(MAX_BODY_BYTES + 1)}, body=b"{}")
    assert result.status == 413
    assert result.json["error"]["code"] == "payload_too_large"
