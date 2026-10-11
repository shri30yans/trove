"""OAuth token verification and caller identity for Trove's MCP resource."""

from __future__ import annotations

import time

import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier

from app import supabase_auth
from app.auth import VerifiedSubject, verify_bearer_token
from app.config import get_config
from app.db import fetchrow
from app.errors import ApiError


class SupabaseTokenVerifier(TokenVerifier):
    """Accept OAuth tokens issued specifically for Trove's MCP resource."""

    async def verify_token(self, token: str) -> AccessToken | None:
        resource = get_config().MCP_PUBLIC_URL
        try:
            claims = await verify_bearer_token(token, audience=resource)
        except ApiError as error:
            if error.status_code == 401:
                return None
            raise
        except jwt.PyJWTError:
            return None

        subject = claims.get("sub")
        client_id = claims.get("client_id")
        expires_at = claims.get("exp")
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(client_id, str)
            or not client_id
            or not isinstance(expires_at, int)
            or expires_at <= int(time.time())
        ):
            return None

        if not await supabase_auth.oauth_validate_session(token, subject):
            return None
        account = await fetchrow(
            """SELECT
                 EXISTS(SELECT 1 FROM deleted_auth_subjects WHERE auth_subject=$1) AS deleted,
                 EXISTS(SELECT 1 FROM account_deletion_requests WHERE auth_subject=$1) AS deletion_pending""",
            subject,
        )
        if account is None or account["deleted"] or account["deletion_pending"]:
            return None

        raw_scopes = claims.get("scope")
        return AccessToken(
            token=token,
            client_id=client_id,
            subject=subject,
            scopes=raw_scopes.split() if isinstance(raw_scopes, str) else [],
            expires_at=expires_at,
            resource=resource,
        )


async def current_subject() -> VerifiedSubject:
    """Resolve the verified MCP token's subject without a database round trip.

    The tool's own query resolves the account and enforces deletion state in the same round
    trip, so MCP reads save the lookup `current_principal` used to perform.
    """
    token = get_access_token()
    if token is None or not token.subject:
        raise ValueError("A valid Trove account link is required.")
    return VerifiedSubject(subject=token.subject)


def oauth_client_id(token: AccessToken) -> str:
    """Return the client identity attached by the MCP token verifier."""
    if not token.client_id:
        raise ValueError("This connection cannot be revoked from the current session.")
    return token.client_id
