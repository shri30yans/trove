"""Offline verification for the ported Python backend: route table + ASGI smoke tests.

Needs no Postgres, S3, model download or network access. Authenticated requests cannot be
exercised here because require_auth upserts the user row, exactly as the previous API did.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

os.environ.update(
    RUN_ENV="local",
    DATABASE_URL="postgresql://x:y@127.0.0.1:1/none",
    S3_ENDPOINT="http://127.0.0.1:9000",
    S3_PUBLIC_ENDPOINT="http://127.0.0.1:9000",
    S3_REGION="us-east-1",
    S3_BUCKET="trove",
    S3_ACCESS_KEY="ak",
    S3_SECRET_KEY="sk",
    AUTH_JWKS_URL="https://auth.example.test/.well-known/jwks.json",
    AUTH_ISSUER="https://auth.example.test",
)
sys.path.insert(0, "/Users/shriyansgandhi/Documents/Code/TroveApp")

from app.main import app  # noqa: E402

EXPECTED = {
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/health/embeddings"),
    ("DELETE", "/v1/auth/account"),
    ("GET", "/v1/auth/account/deletion"),
    ("POST", "/v1/auth/account/deletion/cancel"),
    ("POST", "/v1/auth/refresh"),
    ("POST", "/v1/auth/sign-in"),
    ("POST", "/v1/auth/sign-out"),
    ("GET", "/v1/assets/{asset_id}/content"),
    ("GET", "/v1/me"),
    ("GET", "/v1/preferences"),
    ("PATCH", "/v1/preferences"),
    ("GET", "/v1/explore"),
    ("GET", "/v1/updates"),
    ("GET", "/v1/spaces"),
    ("POST", "/v1/spaces"),
    ("PATCH", "/v1/spaces/{space_id}"),
    ("DELETE", "/v1/spaces/{space_id}"),
    ("GET", "/v1/export/markdown"),
    ("GET", "/v1/memories/{memory_id}/preview"),
    ("POST", "/v1/memories/{memory_id}/move"),
    ("GET", "/v1/plan"),
    ("GET", "/v1/processing"),
    ("PUT", "/v1/uploads/{asset_id}/content"),
    ("POST", "/v1/uploads"),
    ("POST", "/v1/uploads/{asset_id}/complete"),
    ("POST", "/v1/memories"),
    ("GET", "/v1/memories"),
    ("GET", "/v1/memories/{memory_id}"),
    ("PATCH", "/v1/memories/{memory_id}"),
    ("DELETE", "/v1/memories/{memory_id}"),
    ("POST", "/v1/memories/{memory_id}/restore"),
    ("POST", "/v1/memories/{memory_id}/retry"),
    ("GET", "/v1/search"),
    ("GET", "/v1/memories/{memory_id}/related"),
    ("PUT", "/v1/memories/{memory_id}/related/{related_id}/feedback"),
}

PROTECTED = [
    ("GET", "/v1/me"),
    ("GET", "/v1/preferences"),
    ("PATCH", "/v1/preferences"),
    ("GET", "/v1/explore"),
    ("GET", "/v1/updates"),
    ("GET", "/v1/spaces"),
    ("POST", "/v1/spaces"),
    ("PATCH", "/v1/spaces/11111111-1111-1111-1111-111111111111"),
    ("DELETE", "/v1/spaces/11111111-1111-1111-1111-111111111111"),
    ("POST", "/v1/uploads"),
    ("POST", "/v1/uploads/11111111-1111-1111-1111-111111111111/complete"),
    ("POST", "/v1/memories"),
    ("GET", "/v1/memories"),
    ("GET", "/v1/memories/11111111-1111-1111-1111-111111111111"),
    ("PATCH", "/v1/memories/11111111-1111-1111-1111-111111111111"),
    ("DELETE", "/v1/memories/11111111-1111-1111-1111-111111111111"),
    ("POST", "/v1/memories/11111111-1111-1111-1111-111111111111/restore"),
    ("POST", "/v1/memories/11111111-1111-1111-1111-111111111111/retry"),
    ("GET", "/v1/search?q=abc"),
    ("GET", "/v1/memories/11111111-1111-1111-1111-111111111111/related"),
    ("PUT", "/v1/memories/11111111-1111-1111-1111-111111111111/related/22222222-2222-2222-2222-222222222222/feedback"),
]

mounted: set[tuple[str, str]] = set()
for route in app.routes:
    for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}):
        mounted.add((method, getattr(route, "path", "")))

print(f"mounted: {len(mounted)}")
print("missing:", sorted(EXPECTED - mounted) or "none")
print("extra:  ", sorted(mounted - EXPECTED) or "none")
assert mounted == EXPECTED, "route table changed"


async def request(
    method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, dict[bytes, bytes], str]:
    raw = b"" if body is None else body
    target, _, query = path.partition("?")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": target,
        "raw_path": target.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(b"host", b"api.local"), (b"content-type", b"application/json"),
                    *[(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]],
        "client": ("127.0.0.1", 5555),
        "server": ("api.local", 80),
    }

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    result: dict = {"status": None, "headers": [], "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
            result["headers"] = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    await app(scope, receive, send)
    return result["status"], dict(result["headers"]), result["body"].decode()


async def show(label: str, method: str, path: str, **kwargs) -> tuple[int, dict[bytes, bytes], str]:
    status, headers, text = await request(method, path, **kwargs)
    print(f"{label:42} -> {status} {text[:110]}")
    return status, headers, text


async def main() -> None:
    status, _, text = await show("health/live", "GET", "/health/live")
    assert status == 200 and json.loads(text) == {"status": "ok"}

    status, headers, text = await show("unauthenticated /v1/memories", "GET", "/v1/memories")
    assert status == 401 and json.loads(text)["error"]["code"] == "unauthorized"
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"
    assert headers[b"referrer-policy"] == b"no-referrer"
    assert b"server" not in headers and b"x-powered-by" not in headers

    status, _, text = await show("unknown route", "GET", "/v1/totally-unknown")
    assert status == 404 and json.loads(text)["error"]["code"] == "not_found"

    await show("openapi.json disabled", "GET", "/openapi.json")
    await show("docs disabled", "GET", "/docs")

    status, _, text = await show("missing bearer", "GET", "/v1/memories")
    assert status == 401 and json.loads(text)["error"]["code"] == "unauthorized"

    status, _, text = await show("removed local sign-in", "POST", "/v1/auth/dev-token",
                                 body=b'{"subject":"local-user"}')
    assert status == 404 and json.loads(text)["error"]["code"] == "not_found"

    status, _, text = await show("removed account creation", "POST", "/v1/auth/sign-up",
                                 body=b'{"email":"reader@example.test","password":"synthetic-password"}')
    assert status == 404 and json.loads(text)["error"]["code"] == "not_found"

    await show("oversized declared body", "POST", "/v1/memories", headers={"content-length": "2000000"})
    await show("search without q", "GET", "/v1/search")
    await show("health/embeddings", "GET", "/health/embeddings")
    await show("health/ready (no database)", "GET", "/health/ready")

    failures = []
    for method, path in PROTECTED:
        status, _, _ = await request(method, path)
        if status != 401:
            failures.append((method, path, status))
    print(f"auth gates: {len(PROTECTED) - len(failures)}/{len(PROTECTED)} answered 401")
    assert not failures, failures


asyncio.run(main())
print("ASGI smoke test OK")
