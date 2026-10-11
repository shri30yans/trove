"""Bearer-token authentication against the Supabase JWKS, the issuer in every environment."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import get_config
from app.db import fetchrow, transaction
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
    embeddings_enabled: bool


class VerifiedSubject(BaseModel):
    """A bearer token whose signature, issuer, and subject are verified, without any database work.

    Resolving this to an app account happens inside the route's own query, so a read that needs the
    caller owns exactly one database round trip instead of one for authentication plus one for the
    read. Deletion and profile-sync checks stay in that same statement; nothing about them is weaker
    for sharing the round trip.
    """

    subject: str
    email: str | None = None
    display_name: str | None = None


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_config().AUTH_JWKS_URL, cache_keys=True, lifespan=300, timeout=5)


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
    return await run_in_threadpool(_verify_with_jwks, token, audience)


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


async def _verified_identity(request: Request) -> tuple[str, str | None, str | None]:
    """Verify the bearer token and return the subject it speaks for, without any database work."""
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
    return subject, _as_str(payload.get("email")), _as_str(payload.get("name"))


async def require_subject(request: Request) -> VerifiedSubject:
    """Verify the bearer token without touching the database.

    The route resolves the returned subject to an account inside its own query, so authentication
    and the read share one database round trip. The token checks here are byte-for-byte the same
    as the principal path: missing, invalid, and OAuth-client tokens fail before any query runs.
    """
    subject, email, display_name = await _verified_identity(request)
    return VerifiedSubject(subject=subject, email=email, display_name=display_name)


# The account-resolution preamble shared by every combined auth-plus-query statement. It mirrors
# `_principal_from_request` with `allow_deleted=False`: tombstoned subjects stay 401,
# deletion-pending subjects stay 403, and the profile upsert only runs when neither flag is set.
# Every statement that splices it in takes the subject, email, and display name as $1, $2, $3, so
# the domain parameters always start at $4. It is an ALL_CAPS constant because route SQL splices
# it into f-strings, where only such constants may appear.
AUTH_SUBJECT_CTE = """status AS (
     SELECT EXISTS(SELECT 1 FROM deleted_auth_subjects WHERE auth_subject=$1) AS deleted,
            EXISTS(SELECT 1 FROM account_deletion_requests WHERE auth_subject=$1) AS deletion_pending
   ), existing AS MATERIALIZED (
     SELECT id, email, display_name FROM app_users WHERE auth_subject=$1
   ), profile AS (
     INSERT INTO app_users (auth_subject, email, display_name)
     SELECT $1, $2, $3 FROM status s LEFT JOIN existing e ON TRUE
     WHERE NOT s.deleted AND NOT s.deletion_pending
       AND (e.id IS NULL
         OR ($2::text IS NOT NULL AND e.email IS DISTINCT FROM $2::text)
         OR ($3::text IS NOT NULL AND e.display_name IS DISTINCT FROM $3::text))
     ON CONFLICT (auth_subject) DO UPDATE SET
       email = COALESCE(EXCLUDED.email, app_users.email),
       display_name = COALESCE(EXCLUDED.display_name, app_users.display_name),
       updated_at = now()
     RETURNING id, email, display_name
   ), auth AS (
     SELECT s.deleted, s.deletion_pending, COALESCE(p.id, e.id) AS user_id
     FROM status s LEFT JOIN existing e ON TRUE LEFT JOIN profile p ON TRUE
   )"""


def resolve_auth_state(row: Mapping[str, Any]) -> uuid.UUID:
    """Enforce the auth outcome a combined query carries on its anchor row, returning the caller.

    Single-row statements select the flags next to their result; list statements carry them on
    every row. Either way the caller checks the anchor before trusting any domain column.
    """
    if row["deleted"]:
        raise ApiError(401, "account_deleted", "This account has been deleted.")
    if row["deletion_pending"]:
        raise ApiError(403, "account_deletion_pending", "Account deletion is pending. Cancel it to keep using Trove.")
    user_id = row["user_id"]
    if user_id is None:  # pragma: no cover - the guarded upsert provides the row
        raise _INVALID_TOKEN
    return user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))


@asynccontextmanager
async def authenticated_transaction(subject: VerifiedSubject) -> AsyncIterator[tuple[Any, uuid.UUID]]:
    """Open a transaction whose first statement resolves the caller, yielding both.

    Multi-statement writes keep their transaction and lose their separate authentication round
    trip: the account resolution runs on the transaction's own connection before the first
    domain statement, and the same deletion gates apply.
    """
    async with transaction() as connection:
        record = await connection.fetchrow(
            f"""WITH {AUTH_SUBJECT_CTE}
                SELECT (SELECT deleted FROM auth) AS deleted,
                  (SELECT deletion_pending FROM auth) AS deletion_pending,
                  (SELECT user_id FROM auth) AS user_id
                FROM auth""",
            subject.subject,
            subject.email,
            subject.display_name,
        )
        if record is None:  # pragma: no cover - the auth anchor always yields exactly one row
            raise ApiError(500, "internal_error", "The request could not be completed.")
        yield connection, resolve_auth_state(dict(record))


async def _principal_from_request(request: Request, *, allow_deleted: bool = False) -> Principal:
    subject, email, display_name = await _verified_identity(request)
    account = await fetchrow(
        """WITH status AS (
             SELECT EXISTS(SELECT 1 FROM deleted_auth_subjects WHERE auth_subject=$1) AS deleted,
                    NOT $4::boolean AND EXISTS(
                      SELECT 1 FROM account_deletion_requests WHERE auth_subject=$1
                    ) AS deletion_pending
           ), existing AS MATERIALIZED (
             SELECT id, email, display_name FROM app_users WHERE auth_subject=$1
           ), profile AS (
             INSERT INTO app_users (auth_subject, email, display_name)
             SELECT $1, $2, $3 FROM status s LEFT JOIN existing e ON TRUE
             WHERE NOT s.deleted AND NOT s.deletion_pending
               AND (e.id IS NULL
                 OR ($2::text IS NOT NULL AND e.email IS DISTINCT FROM $2::text)
                 OR ($3::text IS NOT NULL AND e.display_name IS DISTINCT FROM $3::text))
             ON CONFLICT (auth_subject) DO UPDATE SET
               email = COALESCE(EXCLUDED.email, app_users.email),
               display_name = COALESCE(EXCLUDED.display_name, app_users.display_name),
               updated_at = now()
             RETURNING id, email, display_name
           )
           SELECT s.deleted, s.deletion_pending,
                  COALESCE(p.id, e.id) AS id,
                  COALESCE(p.email, e.email) AS email,
                  COALESCE(p.display_name, e.display_name) AS display_name,
                  COALESCE((SELECT preferences.embeddings_enabled FROM user_preferences preferences
                            WHERE preferences.user_id=COALESCE(p.id,e.id)),false) AS embeddings_enabled
           FROM status s LEFT JOIN existing e ON TRUE LEFT JOIN profile p ON TRUE""",
        subject,
        email,
        display_name,
        allow_deleted,
    )
    if account is None:
        raise _INVALID_TOKEN
    if account["deleted"]:
        if allow_deleted:
            return Principal(
                id="",
                subject=subject,
                email=email,
                displayName=display_name,
                embeddings_enabled=bool(account["embeddings_enabled"]),
            )
        raise ApiError(401, "account_deleted", "This account has been deleted.")
    if account["deletion_pending"]:
        raise ApiError(403, "account_deletion_pending", "Account deletion is pending. Cancel it to keep using Trove.")
    if account["id"] is None:  # pragma: no cover - the guarded upsert provides the first row
        raise _INVALID_TOKEN
    return Principal(
        id=str(account["id"]),
        subject=subject,
        email=account["email"],
        displayName=account["display_name"],
        embeddings_enabled=bool(account["embeddings_enabled"]),
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
