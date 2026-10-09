"""HTTP-level signup/confirmation coverage from the Trove route to the Supabase adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from app import supabase_auth
from app.main import app
from tests.config_fixture import synthetic_config


@pytest.fixture
def auth_provider(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    monkeypatch.setattr(
        supabase_auth,
        "get_config",
        lambda: synthetic_config(
            SUPABASE_URL="https://project.example.test",
            AUTH_JWKS_URL="https://project.example.test/auth/v1/.well-known/jwks.json",
            AUTH_ISSUER="https://project.example.test/auth/v1",
        ),
    )
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/auth/v1/signup":
            return httpx.Response(200, json={"id": "synthetic-user", "access_token": None, "refresh_token": None})
        if request.url.path == "/auth/v1/resend":
            return httpx.Response(200, json={})
        if request.url.path == "/auth/v1/verify":
            return httpx.Response(
                200,
                json={
                    "id": "synthetic-user",
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                    "token_type": "bearer",
                },
            )
        return httpx.Response(404, json={"msg": "unexpected synthetic endpoint"})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(supabase_auth, "_client", lambda: httpx.AsyncClient(transport=transport))
    return requests


@pytest.mark.asyncio
async def test_signup_resend_and_confirmation_cross_the_http_and_provider_boundaries(
    auth_provider: list[httpx.Request],
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://trove.test") as client:
        signup = await client.post(
            "/v1/auth/sign-up",
            json={"email": "reader@example.com", "password": "synthetic-password"},
        )
        resend = await client.post("/v1/auth/resend-confirmation", json={"email": "reader@example.com"})
        confirmed = await client.post("/v1/auth/confirm-email", json={"token_hash": "synthetic-token-hash"})

    assert signup.status_code == 200
    assert signup.json() == {"status": "email_confirmation_required"}
    assert resend.status_code == 200
    assert resend.json() == {"status": "confirmation_email_requested"}
    assert confirmed.status_code == 200
    assert confirmed.headers["cache-control"] == "no-store"
    assert confirmed.headers["pragma"] == "no-cache"
    assert confirmed.json() == {
        "status": "authenticated",
        "session": {"accessToken": "access", "refreshToken": "refresh", "expiresIn": 3600, "tokenType": "Bearer"},
    }

    assert [request.url.path for request in auth_provider] == [
        "/auth/v1/signup",
        "/auth/v1/resend",
        "/auth/v1/verify",
    ]
    assert auth_provider[0].url.params["redirect_to"] == "http://localhost:4000/v1/auth/confirm-email"
    assert auth_provider[1].url.params["redirect_to"] == "http://localhost:4000/v1/auth/confirm-email"
    assert json.loads(auth_provider[1].content) == {"type": "signup", "email": "reader@example.com"}
    assert json.loads(auth_provider[2].content) == {"type": "signup", "token_hash": "synthetic-token-hash"}
    assert "access_token" not in signup.text


@pytest.mark.asyncio
async def test_confirmation_landing_is_a_safe_browser_fallback() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://trove.test") as client:
        response = await client.get("/v1/auth/confirm-email")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "nonce-" in response.headers["content-security-policy"]
    assert "Email confirmed" in response.text
    assert "trove://confirm-email" in response.text
    assert "access_token" in response.text
    assert "refresh_token" in response.text


def test_confirmation_email_template_targets_trove_and_keeps_provider_contract() -> None:
    from pathlib import Path

    template = (Path(__file__).parents[1] / "email-templates" / "confirmation.html").read_text()

    assert "{{ .RedirectTo }}#token_hash={{ .TokenHash }}&amp;type=signup" in template
    assert "{{ .ConfirmationURL }}" in template


@pytest.mark.asyncio
async def test_resend_keeps_unknown_accounts_neutral_and_does_not_leak_provider_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = synthetic_config(
        SUPABASE_URL="https://project.example.test",
        AUTH_JWKS_URL="https://project.example.test/auth/v1/.well-known/jwks.json",
        AUTH_ISSUER="https://project.example.test/auth/v1",
    )
    monkeypatch.setattr(supabase_auth, "get_config", lambda: config)
    transport = httpx.MockTransport(lambda _request: httpx.Response(404, json={"msg": "private provider detail"}))
    monkeypatch.setattr(supabase_auth, "_client", lambda: httpx.AsyncClient(transport=transport))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://trove.test") as client:
        response = await client.post("/v1/auth/resend-confirmation", json={"email": "unknown@example.com"})

    assert response.status_code == 200
    assert response.json() == {"status": "confirmation_email_requested"}
    assert "private provider detail" not in response.text


@pytest.mark.asyncio
async def test_invalid_resend_body_is_rejected_before_any_provider_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def provider_must_not_be_called(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(supabase_auth, "resend_confirmation", provider_must_not_be_called)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://trove.test") as client:
        response = await client.post("/v1/auth/resend-confirmation", json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_auth_request"
    assert not called
