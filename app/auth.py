"""Bearer-token authentication against the Supabase JWKS, plus the local development issuer."""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import get_config
from app.db import fetchrow, fetchval
from app.errors import ApiError

# Only asymmetric algorithms are accepted from a remote JWKS so that a public key can never be
# mistaken for an HMAC secret.
_JWKS_ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA")
_UNAUTHORIZED = ApiError(401, "unauthorized", "A bearer token is required.")
_INVALID_TOKEN = ApiError(401, "invalid_token", "The bearer token is invalid or expired.")
# A sign-in provider that cannot be reached is an outage, not a bad credential. Telling the two
# apart is what lets the client keep its token and retry instead of logging the user out.
_AUTH_UNAVAILABLE = ApiError(503, "auth_unavailable", "The sign-in service is unavailable. Try again.")


class Principal(BaseModel):
    id: str
    subject: str
    email: str | None = None
    displayName: str | None = None


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    config = get_config()
    if not config.AUTH_JWKS_URL:
        raise _AUTH_UNAVAILABLE
    return jwt.PyJWKClient(config.AUTH_JWKS_URL, cache_keys=True, lifespan=300, timeout=5)


def _verify_with_jwks(token: str, audience: str | None = None) -> dict[str, Any]:
    config = get_config()
    try:
        key = _jwks_client().get_signing_key_from_jwt(token)
    except (jwt.PyJWKClientConnectionError, jwt.PyJWKSetError) as error:
        # Unreachable or unreadable JWKS is our outage; an unknown kid stays a 401 below.
        raise _AUTH_UNAVAILABLE from error
    # PyJWK derives HS256 from a kty of "oct"; refusing one here closes the algorithm-confusion
    # door even if a future provider ever publishes a symmetric key in its JWKS.
    if key.key_type == "oct":
        raise _INVALID_TOKEN
    return jwt.decode(
        token,
        key.key,
        algorithms=list(_JWKS_ALGORITHMS),
        audience=audience or config.AUTH_AUDIENCE,
        issuer=config.AUTH_ISSUER,
        leeway=30,
    )


async def verify_bearer_token(token: str, *, audience: str | None = None) -> dict[str, Any]:
    config = get_config()
    if config.AUTH_JWKS_URL:
        return await run_in_threadpool(_verify_with_jwks, token, audience)
    raise _AUTH_UNAVAILABLE


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _profile_changed(row: dict[str, Any] | None, email: str | None, display_name: str | None) -> bool:
    """Whether the row on file still says what this token says.

    The alternative is an INSERT..ON CONFLICT on every authenticated request, which takes a lock on
    the user's row and rewrites updated_at just because they opened their archive.
    """
    if row is None:
        return True
    claims = ((email, "email"), (display_name, "display_name"))
    return any(claim is not None and claim != row[column] for claim, column in claims)


async def _load_principal(subject: str, email: str | None, display_name: str | None) -> Principal:
    row = await fetchrow("SELECT id, email, display_name FROM app_users WHERE auth_subject=$1", subject)
    if _profile_changed(row, email, display_name):
        # First sight of this subject, or the provider says the profile moved.
        row = await fetchrow(
            """INSERT INTO app_users (auth_subject, email, display_name)
               VALUES ($1, $2, $3)
               ON CONFLICT (auth_subject) DO UPDATE SET
                 email = COALESCE(EXCLUDED.email, app_users.email),
                 display_name = COALESCE(EXCLUDED.display_name, app_users.display_name),
                 updated_at = now()
               RETURNING id, email, display_name""",
            subject,
            email,
            display_name,
        )
    if row is None:  # pragma: no cover - the upsert always returns a row
        raise _INVALID_TOKEN
    return Principal(
        id=str(row["id"]),
        subject=subject,
        email=row["email"],
        displayName=row["display_name"],
    )


async def _principal_from_request(request: Request, *, allow_deleted: bool = False) -> Principal:
    header = request.headers.get("authorization")
    if not header or not header.startswith("Bearer "):
        raise _UNAUTHORIZED
    token = header[len("Bearer ") :].strip()
    if not token:
        raise _UNAUTHORIZED
    try:
        payload = await verify_bearer_token(token)
    except ApiError:
        raise
    except jwt.PyJWTError as error:
        raise _INVALID_TOKEN from error
    if isinstance(payload.get("client_id"), str):
        raise ApiError(
            403,
            "oauth_client_restricted",
            "OAuth-linked clients can access Trove only through their granted integration tools.",
        )
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise _INVALID_TOKEN
    if await fetchval("SELECT 1 FROM deleted_auth_subjects WHERE auth_subject=$1", subject):
        if allow_deleted:
            return Principal(
                id="",
                subject=subject,
                email=_as_str(payload.get("email")),
                displayName=_as_str(payload.get("name")),
            )
        raise ApiError(401, "account_deleted", "This account has been deleted.")
    if not allow_deleted and await fetchval("SELECT 1 FROM account_deletion_requests WHERE auth_subject=$1", subject):
        raise ApiError(403, "account_deletion_pending", "Account deletion is pending. Cancel it to keep using Trove.")
    return await _load_principal(
        subject,
        _as_str(payload.get("email")),
        _as_str(payload.get("name")),
    )


async def require_auth(request: Request) -> Principal:
    return await _principal_from_request(request)


async def require_account_deletion_auth(request: Request) -> Principal:
    """Allow a tombstoned subject to retry cleanup after a partial provider outage."""
    return await _principal_from_request(request, allow_deleted=True)


def as_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise ApiError(400, "invalid_id", "The identifier is not a valid UUID.") from error
