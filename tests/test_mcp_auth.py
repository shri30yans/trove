from __future__ import annotations

from unittest.mock import AsyncMock

from app import mcp_auth
from app.config import Config
from tests.config_fixture import synthetic_config


def _config() -> Config:
    return synthetic_config(MCP_PUBLIC_URL="https://api.trove.example.test/mcp")


async def test_verifier_requires_mcp_audience_and_preserves_oauth_client_and_user(
    monkeypatch,
) -> None:
    config = _config()
    claims = {
        "sub": "auth-user-123",
        "client_id": "oauth-client-456",
        "aud": config.MCP_PUBLIC_URL,
        "exp": 4_102_444_800,
        "scope": "openid email",
    }
    verify = AsyncMock(return_value=claims)
    session_is_active = AsyncMock(return_value=True)
    account_state = AsyncMock(return_value={"deleted": False, "deletion_pending": False})
    monkeypatch.setattr(mcp_auth, "get_config", lambda: config)
    monkeypatch.setattr(mcp_auth, "verify_bearer_token", verify)
    monkeypatch.setattr(mcp_auth.supabase_auth, "oauth_validate_session", session_is_active)
    monkeypatch.setattr(mcp_auth, "fetchrow", account_state)

    access_token = await mcp_auth.SupabaseTokenVerifier().verify_token("signed-mcp-token")

    assert access_token is not None
    assert access_token.client_id == "oauth-client-456"
    assert access_token.subject == "auth-user-123"
    assert access_token.resource == config.MCP_PUBLIC_URL
    assert access_token.scopes == ["openid", "email"]
    verify.assert_awaited_once_with("signed-mcp-token", audience=config.MCP_PUBLIC_URL)
    account_state.assert_awaited_once()


async def test_verifier_rejects_deleted_or_deleting_accounts(monkeypatch) -> None:
    config = _config()
    monkeypatch.setattr(mcp_auth, "get_config", lambda: config)
    monkeypatch.setattr(
        mcp_auth,
        "verify_bearer_token",
        AsyncMock(
            return_value={
                "sub": "auth-user-123",
                "client_id": "oauth-client-456",
                "exp": 4_102_444_800,
            }
        ),
    )
    monkeypatch.setattr(mcp_auth.supabase_auth, "oauth_validate_session", AsyncMock(return_value=True))
    monkeypatch.setattr(
        mcp_auth,
        "fetchrow",
        AsyncMock(return_value={"deleted": False, "deletion_pending": True}),
    )

    assert await mcp_auth.SupabaseTokenVerifier().verify_token("signed-mcp-token") is None
