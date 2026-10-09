"""Supabase Auth proxy contracts, exercised with isolated synthetic responses."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app import supabase_auth
from app.config import Config
from app.errors import ApiError


def _config() -> Config:
    return Config(
        RUN_ENV="local",
        DATABASE_URL="postgresql://u:p@127.0.0.1:5432/trove",
        S3_ENDPOINT="http://127.0.0.1:54321",
        S3_REGION="local",
        S3_BUCKET="trove-private",
        S3_ACCESS_KEY="test",
        S3_SECRET_KEY="test",
        AUTH_JWKS_URL="https://project.example.test/auth/v1/.well-known/jwks.json",
        AUTH_ISSUER="https://project.example.test/auth/v1",
        SUPABASE_URL="https://project.example.test",
        SUPABASE_AUTH_API_KEY="publishable-test-key",
        SUPABASE_SECRET_KEY="server-only-service-role-key",
    )


def _install_provider(monkeypatch: pytest.MonkeyPatch, status: int, payload: dict[str, Any]) -> list[httpx.Request]:
    config = _config()
    monkeypatch.setattr(supabase_auth, "get_config", lambda: config)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=payload)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(supabase_auth, "_client", lambda: httpx.AsyncClient(transport=transport))
    return requests


@pytest.mark.asyncio
async def test_sign_in_proxies_credentials_and_returns_only_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _install_provider(
        monkeypatch,
        200,
        {"access_token": "access-test", "refresh_token": "refresh-test", "expires_in": 3600, "token_type": "bearer"},
    )

    result = await supabase_auth.sign_in("user@example.test", "synthetic-password")

    assert result == {
        "status": "authenticated",
        "session": {
            "accessToken": "access-test",
            "refreshToken": "refresh-test",
            "expiresIn": 3600,
            "tokenType": "Bearer",
        },
    }
    assert requests[0].url.path == "/auth/v1/token"
    assert requests[0].url.params["grant_type"] == "password"
    assert requests[0].headers["apikey"] == "publishable-test-key"
    assert json.loads(requests[0].content) == {"email": "user@example.test", "password": "synthetic-password"}


@pytest.mark.asyncio
async def test_sign_in_does_not_expose_provider_error_details(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(monkeypatch, 400, {"msg": "secret provider detail"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_in("user@example.test", "wrong-password")

    assert raised.value.status_code == 401
    assert raised.value.code == "invalid_credentials"
    assert "secret provider detail" not in raised.value.message


@pytest.mark.asyncio
async def test_sign_up_returns_session_when_email_confirmation_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _install_provider(
        monkeypatch,
        200,
        {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600, "token_type": "bearer"},
    )

    result = await supabase_auth.sign_up("new@example.test", "synthetic-password")

    assert result["status"] == "authenticated"
    assert result["session"]["accessToken"] == "new-access"
    assert requests[0].url.path == "/auth/v1/signup"
    assert json.loads(requests[0].content) == {"email": "new@example.test", "password": "synthetic-password"}


@pytest.mark.asyncio
async def test_sign_up_reports_email_confirmation_when_provider_returns_no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(monkeypatch, 200, {"id": "new-user", "access_token": None, "refresh_token": None})

    assert await supabase_auth.sign_up("new@example.test", "synthetic-password") == {
        "status": "email_confirmation_required"
    }


@pytest.mark.asyncio
async def test_password_reset_uses_the_trove_deep_link_and_does_not_inspect_account_existence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _install_provider(monkeypatch, 200, {})

    await supabase_auth.request_password_reset("reader@example.test")

    assert requests[0].url.path == "/auth/v1/recover"
    assert requests[0].url.params["redirect_to"] == "trove://reset-password"
    assert json.loads(requests[0].content) == {"email": "reader@example.test"}


@pytest.mark.asyncio
async def test_password_update_uses_recovery_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _install_provider(monkeypatch, 200, {"id": "user-id"})

    await supabase_auth.update_password("recovery-access", "new-synthetic-password")

    assert requests[0].method == "PUT"
    assert requests[0].url.path == "/auth/v1/user"
    assert requests[0].headers["authorization"] == "Bearer recovery-access"
    assert json.loads(requests[0].content) == {"password": "new-synthetic-password"}


@pytest.mark.asyncio
async def test_refresh_rotates_the_supabase_session(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _install_provider(
        monkeypatch,
        200,
        {"access_token": "next-access", "refresh_token": "next-refresh", "expires_in": 1800, "token_type": "bearer"},
    )

    result = await supabase_auth.refresh("previous-refresh")

    assert result["session"]["refreshToken"] == "next-refresh"
    assert json.loads(requests[0].content) == {"refresh_token": "previous-refresh"}


@pytest.mark.asyncio
async def test_account_deletion_uses_the_server_only_admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = "00000000-0000-0000-0000-000000000123"
    requests = _install_provider(monkeypatch, 200, {"id": user_id})

    await supabase_auth.delete_user(user_id)

    request = requests[0]
    assert request.method == "DELETE"
    assert request.url.path == f"/auth/v1/admin/users/{user_id}"
    assert request.headers["apikey"] == "server-only-service-role-key"
    assert "authorization" not in request.headers


@pytest.mark.asyncio
async def test_account_deletion_rejects_non_uuid_provider_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supabase_auth, "get_config", _config)

    with pytest.raises(ApiError) as raised:
        await supabase_auth.delete_user("not-a-provider-user-id")

    assert raised.value.code == "account_deletion_unavailable"


@pytest.mark.asyncio
async def test_unavailable_supabase_is_reported_as_an_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(monkeypatch, 503, {"msg": "provider detail"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_in("user@example.test", "synthetic-password")

    assert raised.value.status_code == 503
    assert raised.value.code == "auth_unavailable"


@pytest.mark.asyncio
async def test_missing_provider_configuration_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        supabase_auth,
        "get_config",
        lambda: _config().model_copy(update={"SUPABASE_URL": None, "SUPABASE_AUTH_API_KEY": None}),
    )

    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_in("user@example.test", "synthetic-password")

    assert raised.value.status_code == 503
    assert raised.value.code == "auth_not_configured"
