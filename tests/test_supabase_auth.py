"""Supabase Auth proxy contracts, exercised with isolated synthetic responses."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app import supabase_auth
from app.config import Config
from app.errors import ApiError
from tests.config_fixture import synthetic_config


def _config() -> Config:
    return synthetic_config(
        SUPABASE_URL="https://project.example.test",
        AUTH_JWKS_URL="https://project.example.test/auth/v1/.well-known/jwks.json",
        AUTH_ISSUER="https://project.example.test/auth/v1",
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


def test_confirmation_redirect_uses_the_public_api_origin_without_mcp_path(monkeypatch: pytest.MonkeyPatch) -> None:
    config = synthetic_config(MCP_PUBLIC_URL="https://api.example.test/mcp/")
    monkeypatch.setattr(supabase_auth, "get_config", lambda: config)

    assert supabase_auth.confirmation_redirect_url() == "https://api.example.test/v1/auth/confirm-email"


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
async def test_sign_in_reports_unconfirmed_email_distinctly_from_wrong_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_provider(monkeypatch, 400, {"error_code": "email_not_confirmed", "msg": "Email not confirmed"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_in("user@example.test", "synthetic-password")

    assert raised.value.status_code == 403
    assert raised.value.code == "email_not_confirmed"
    assert "confirm" in raised.value.message.lower()


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
async def test_sign_up_reports_email_confirmation_when_provider_returns_no_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_provider(monkeypatch, 200, {"id": "new-user", "access_token": None, "refresh_token": None})

    assert await supabase_auth.sign_up("new@example.test", "synthetic-password") == {
        "status": "email_confirmation_required"
    }


@pytest.mark.asyncio
async def test_sign_up_reports_a_provider_email_failure_as_email_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    """GoTrue hides both outcomes behind `unexpected_failure`, so the copy must still say why."""
    _install_provider(monkeypatch, 500, {"error_code": "unexpected_failure", "msg": "Error sending confirmation email"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_up("new@example.test", "synthetic-password")

    assert raised.value.status_code == 503
    assert raised.value.code == "auth_email_unavailable"
    assert "confirmation email" in raised.value.message


@pytest.mark.asyncio
async def test_sign_up_reports_an_exhausted_email_budget_as_email_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(
        monkeypatch, 429, {"error_code": "over_email_send_rate_limit", "msg": "email rate limit exceeded"}
    )

    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_up("new@example.test", "synthetic-password")

    assert raised.value.code == "auth_email_unavailable"


@pytest.mark.asyncio
async def test_sign_up_deep_links_confirmation_back_to_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _install_provider(
        monkeypatch,
        200,
        {"id": "new-user", "access_token": None, "refresh_token": None},
    )

    assert await supabase_auth.sign_up("new@example.test", "synthetic-password") == {
        "status": "email_confirmation_required"
    }
    assert requests[0].url.params["redirect_to"] == "http://localhost:4000/v1/auth/confirm-email"


@pytest.mark.asyncio
async def test_resend_confirmation_targets_the_signup_flow_with_the_app_deep_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _install_provider(monkeypatch, 200, {})

    await supabase_auth.resend_confirmation("pending@example.test")

    assert requests[0].url.path == "/auth/v1/resend"
    assert requests[0].url.params["redirect_to"] == "http://localhost:4000/v1/auth/confirm-email"
    assert json.loads(requests[0].content) == {"type": "signup", "email": "pending@example.test"}


@pytest.mark.asyncio
async def test_resend_confirmation_maps_nothing_to_send_to_a_neutral_not_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_provider(monkeypatch, 404, {"msg": "User not found"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.resend_confirmation("unknown@example.test")

    assert raised.value.code == "email_not_pending"


@pytest.mark.asyncio
async def test_resend_confirmation_rate_limit_is_a_retryable_429(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(
        monkeypatch, 429, {"error_code": "over_email_send_rate_limit", "msg": "email rate limit exceeded"}
    )

    with pytest.raises(ApiError) as raised:
        await supabase_auth.resend_confirmation("pending@example.test")

    assert raised.value.status_code == 429
    assert raised.value.code == "confirmation_rate_limited"


@pytest.mark.asyncio
async def test_confirm_email_verifies_the_signup_token_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _install_provider(monkeypatch, 200, {"id": "confirmed-user"})

    await supabase_auth.confirm_email("synthetic-token-hash")

    assert requests[0].url.path == "/auth/v1/verify"
    assert json.loads(requests[0].content) == {"type": "signup", "token_hash": "synthetic-token-hash"}


@pytest.mark.asyncio
async def test_confirm_email_returns_the_provider_session_when_supplied(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _install_provider(
        monkeypatch,
        200,
        {
            "id": "confirmed-user",
            "access_token": "callback-access",
            "refresh_token": "callback-refresh",
            "expires_in": 3600,
            "token_type": "bearer",
        },
    )

    result = await supabase_auth.confirm_email("synthetic-token-hash")

    assert result == {
        "status": "authenticated",
        "session": {
            "accessToken": "callback-access",
            "refreshToken": "callback-refresh",
            "expiresIn": 3600,
            "tokenType": "Bearer",
        },
    }
    assert requests[0].url.path == "/auth/v1/verify"


@pytest.mark.asyncio
async def test_confirm_email_maps_an_expired_link(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(monkeypatch, 400, {"msg": "Token has expired or is invalid"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.confirm_email("stale-token-hash")

    assert raised.value.status_code == 400
    assert raised.value.code == "email_link_expired"


@pytest.mark.asyncio
async def test_confirm_email_maps_an_invalid_link(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(monkeypatch, 400, {"msg": "Invalid token"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.confirm_email("bad-token-hash")

    assert raised.value.code == "email_link_invalid"


@pytest.mark.asyncio
async def test_password_reset_reports_a_provider_email_failure_as_email_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_provider(monkeypatch, 500, {"error_code": "unexpected_failure", "msg": "Error sending recovery email"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.request_password_reset("user@example.test")

    assert raised.value.code == "auth_email_unavailable"


@pytest.mark.asyncio
async def test_sign_in_failures_never_take_the_email_delivery_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(
        monkeypatch, 429, {"error_code": "over_email_send_rate_limit", "msg": "email rate limit exceeded"}
    )

    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_in("user@example.test", "wrong-password")

    assert raised.value.code == "auth_rate_limited"

    _install_provider(monkeypatch, 500, {"error_code": "unexpected_failure", "msg": "Error sending confirmation email"})
    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_in("user@example.test", "wrong-password")

    assert raised.value.code == "auth_unavailable"


@pytest.mark.asyncio
async def test_unrelated_provider_failures_stay_outages(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_provider(monkeypatch, 500, {"error_code": "unexpected_failure", "msg": "Database error saving new user"})

    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_up("new@example.test", "synthetic-password")

    assert raised.value.code == "auth_unavailable"


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
async def test_a_credential_less_config_cannot_be_built_so_the_proxy_never_checks_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boot gate owns this, which is why `sign_in` has no "not configured" branch."""
    with pytest.raises(ValidationError):
        synthetic_config(SUPABASE_URL="", SUPABASE_AUTH_API_KEY="")

    _install_provider(monkeypatch, 400, {"msg": "Invalid login credentials"})
    with pytest.raises(ApiError) as raised:
        await supabase_auth.sign_in("user@example.test", "wrong-password")
    assert raised.value.code == "invalid_credentials"
