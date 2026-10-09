"""Auth verification, tested offline with synthetic keys.

Nothing here reaches the network or Postgres: the JWKS client is replaced with one that hands
back a generated key, and the principal lookup is replaced with a row. What is real is the token
itself, so a wrong PyJWT call signature fails here the way it would in production.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from jwt.utils import base64url_encode

from app import auth
from app.config import Config
from app.errors import ApiError
from tests.config_fixture import COMPLETE_CONFIG, synthetic_config

_ISSUER = "https://trove.example.test/auth/v1"
_AUDIENCE = "authenticated"

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_PEM = (
    _PRIVATE_KEY.public_key()
    .public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode("ascii")
)
_RSA_JWK: dict[str, Any] = {**json.loads(RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key())), "kid": "key-1", "use": "sig"}


def _config(**overrides: Any) -> Config:
    values: dict[str, Any] = {
        "AUTH_AUDIENCE": _AUDIENCE,
        "AUTH_ISSUER": _ISSUER,
        **COMPLETE_CONFIG,
    }
    values.update(overrides)
    return synthetic_config(**values)


@pytest.fixture
def install_config(monkeypatch):
    def install(**overrides: Any) -> Config:
        config = _config(**overrides)
        monkeypatch.setattr(auth, "get_config", lambda: config)
        return config

    return install


class _FakeJwksClient:
    """Stands in for PyJWKClient, which would otherwise fetch the key set over the network."""

    def __init__(self, key: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self._key = key
        self._error = error

    def get_signing_key_from_jwt(self, _token: str) -> jwt.PyJWK:
        if self._error is not None:
            raise self._error
        assert self._key is not None
        return jwt.PyJWK.from_dict(self._key)


@pytest.fixture
def jwks(monkeypatch, install_config):
    def use(key: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        install_config()
        client = _FakeJwksClient(key, error)
        monkeypatch.setattr(auth, "_jwks_client", lambda: client)

    return use


def _rs256_token(**claims: Any) -> str:
    now = dt.datetime.now(dt.UTC)
    payload: dict[str, Any] = {
        "sub": "auth0|user-1",
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + dt.timedelta(hours=1),
        "email": "reader@trove.example.test",
        "name": "Reader",
    }
    payload.update(claims)
    return jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256", headers={"kid": "key-1", "typ": "JWT"})


class _Request:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


class _Rows:
    """Answers the account lookup and records its arguments without a database."""

    def __init__(
        self,
        *,
        exists: bool = True,
        email: str | None = None,
        display_name: str | None = None,
        embeddings_enabled: bool = False,
    ) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.exists = exists
        self.embeddings_enabled = embeddings_enabled
        self.profile: dict[str, Any] = {"email": email, "display_name": display_name}

    async def __call__(self, sql: str, *args: Any) -> dict[str, Any] | None:
        self.statements.append((" ".join(sql.split()), args))
        statement = sql.lstrip().upper()
        if statement.startswith("WITH"):
            if (
                not self.exists
                or (args[1] is not None and args[1] != self.profile["email"])
                or (args[2] is not None and args[2] != self.profile["display_name"])
            ):
                self.exists = True
                self.profile = {
                    "email": args[1] or self.profile["email"],
                    "display_name": args[2] or self.profile["display_name"],
                }
            return {
                "deleted": False,
                "deletion_pending": False,
                "id": str(uuid.UUID(int=7)),
                "embeddings_enabled": self.embeddings_enabled,
                **self.profile,
            }
        if statement.startswith("SELECT"):
            if not self.exists:
                return None
            return {"id": str(uuid.UUID(int=7)), **self.profile}
        self.profile = {
            "email": args[1] or self.profile["email"],
            "display_name": args[2] or self.profile["display_name"],
        }
        return {"id": str(uuid.UUID(int=7)), **self.profile}


async def test_local_hmac_tokens_are_not_accepted_as_provider_sessions(
    install_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_config()
    monkeypatch.setattr(auth, "_jwks_client", lambda: _FakeJwksClient(error=jwt.PyJWKSetError("unknown key")))
    now = dt.datetime.now(dt.UTC)
    forged = jwt.encode(
        {
            "sub": "local-user",
            "iss": "trove-local-dev",
            "aud": _AUDIENCE,
            "iat": now,
            "exp": now + dt.timedelta(hours=1),
        },
        "legacy-local-secret-long-enough-for-hs256",
        algorithm="HS256",
    )
    with pytest.raises(ApiError) as raised:
        await auth.verify_bearer_token(forged)
    assert raised.value.status_code == 503
    assert raised.value.code == "auth_unavailable"


async def test_a_public_key_cannot_sign_a_token_the_verifier_accepts(jwks) -> None:
    jwks(key=_RSA_JWK)
    # The algorithm-confusion attack: HS256 with the public key used as the HMAC secret. PyJWT
    # refuses to encode that combination, so the forged token is assembled by hand here.
    confused = _forge_hs256(_PUBLIC_PEM.encode(), {"sub": "attacker", "aud": _AUDIENCE, "iss": _ISSUER})
    with pytest.raises(jwt.InvalidAlgorithmError):
        auth._verify_with_jwks(confused)


async def test_bearer_verification_can_require_a_resource_specific_audience(jwks) -> None:
    jwks(key=_RSA_JWK)
    resource = "https://api.trove.example.test/mcp"
    token = _rs256_token(aud=resource)

    claims = await auth.verify_bearer_token(token, audience=resource)

    assert claims["aud"] == resource
    with pytest.raises(jwt.InvalidAudienceError):
        await auth.verify_bearer_token(token)


def _forge_hs256(secret: bytes, payload: dict[str, Any]) -> str:
    def segment(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = segment(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "key-1"}).encode())
    body = segment(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode()
    signature = segment(hmac.new(secret, signing_input, hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


async def test_a_key_the_provider_publishes_for_real_still_verifies(jwks) -> None:
    jwks(key=_RSA_JWK)
    assert auth._verify_with_jwks(_rs256_token())["email"] == "reader@trove.example.test"


async def test_a_symmetric_key_in_the_jwks_is_refused_before_it_is_used(jwks) -> None:
    secret = uuid.uuid4().bytes + uuid.uuid4().bytes
    jwks(key={"kty": "oct", "kid": "key-1", "k": base64url_encode(secret), "alg": "HS256"})
    token = jwt.encode({"sub": "attacker", "aud": _AUDIENCE, "iss": _ISSUER}, secret, algorithm="HS256")
    with pytest.raises(ApiError) as raised:
        auth._verify_with_jwks(token)
    assert raised.value.status_code == 401


async def test_a_token_from_another_issuer_is_refused(jwks) -> None:
    jwks(key=_RSA_JWK)
    with pytest.raises(jwt.InvalidIssuerError):
        auth._verify_with_jwks(_rs256_token(iss="https://elsewhere.example.test"))


async def test_a_token_for_another_audience_is_refused(jwks) -> None:
    jwks(key=_RSA_JWK)
    with pytest.raises(jwt.InvalidAudienceError):
        auth._verify_with_jwks(_rs256_token(aud="something-else"))


async def test_an_expired_token_is_refused(jwks) -> None:
    jwks(key=_RSA_JWK)
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
    with pytest.raises(jwt.ExpiredSignatureError):
        auth._verify_with_jwks(_rs256_token(iat=past, exp=past + dt.timedelta(minutes=5)))


async def test_an_unreachable_jwks_is_an_outage_and_not_a_bad_token(jwks) -> None:
    jwks(error=jwt.PyJWKClientConnectionError("could not fetch the keys"))
    with pytest.raises(ApiError) as raised:
        auth._verify_with_jwks(_rs256_token())
    assert raised.value.status_code == 503
    assert raised.value.code == "auth_unavailable"


async def test_an_unknown_kid_stays_a_rejected_token(jwks) -> None:
    jwks(error=jwt.PyJWKClientError("kid: key-1 not found in jwks"))
    with pytest.raises(jwt.PyJWKClientError):
        auth._verify_with_jwks(_rs256_token())


async def test_require_auth_carries_a_verified_token_into_a_principal(jwks, monkeypatch) -> None:
    jwks(key=_RSA_JWK)
    rows = _Rows(exists=False)
    monkeypatch.setattr(auth, "fetchrow", rows)
    principal = await auth.require_auth(_Request({"authorization": f"Bearer {_rs256_token()}"}))
    assert principal.subject == "auth0|user-1"
    assert principal.email == "reader@trove.example.test"
    assert principal.displayName == "Reader"
    assert principal.embeddings_enabled is False


async def test_auth_loads_embedding_preference_with_the_account_lookup(jwks, monkeypatch) -> None:
    jwks(key=_RSA_JWK)
    rows = _Rows(embeddings_enabled=True)
    monkeypatch.setattr(auth, "fetchrow", rows)

    principal = await auth.require_auth(_Request({"authorization": f"Bearer {_rs256_token()}"}))

    assert principal.embeddings_enabled is True
    assert len(rows.statements) == 1
    assert "FROM user_preferences preferences" in rows.statements[0][0]


async def test_a_first_request_for_a_subject_creates_it_once(jwks, monkeypatch) -> None:
    jwks(key=_RSA_JWK)
    rows = _Rows(exists=False)
    monkeypatch.setattr(auth, "fetchrow", rows)
    await auth.require_auth(_Request({"authorization": f"Bearer {_rs256_token()}"}))
    assert len(rows.statements) == 1
    assert rows.statements[0][1] == ("auth0|user-1", "reader@trove.example.test", "Reader", False)
    assert "ON CONFLICT (auth_subject) DO UPDATE" in rows.statements[0][0]
    assert "deleted_auth_subjects" in rows.statements[0][0]
    assert "account_deletion_requests" in rows.statements[0][0]


async def test_a_request_that_changes_nothing_writes_nothing(jwks, monkeypatch) -> None:
    jwks(key=_RSA_JWK)
    rows = _Rows(email="reader@trove.example.test", display_name="Reader")
    monkeypatch.setattr(auth, "fetchrow", rows)
    principal = await auth.require_auth(_Request({"authorization": f"Bearer {_rs256_token()}"}))
    # The upsert used to run here, locking the row and rewriting updated_at on every read.
    assert len(rows.statements) == 1
    assert principal.id == str(uuid.UUID(int=7))


async def test_a_moved_email_or_name_is_written_back_once(jwks, monkeypatch) -> None:
    jwks(key=_RSA_JWK)
    rows = _Rows(email="old@trove.example.test", display_name="Reader")
    monkeypatch.setattr(auth, "fetchrow", rows)
    principal = await auth.require_auth(_Request({"authorization": f"Bearer {_rs256_token()}"}))
    assert len(rows.statements) == 1
    assert principal.email == "reader@trove.example.test"


async def test_a_token_without_profile_claims_does_not_blank_the_stored_profile(jwks, monkeypatch) -> None:
    jwks(key=_RSA_JWK)
    rows = _Rows(email="reader@trove.example.test", display_name="Reader")
    monkeypatch.setattr(auth, "fetchrow", rows)
    token = _rs256_token(email=None, name=None)
    principal = await auth.require_auth(_Request({"authorization": f"Bearer {token}"}))
    assert len(rows.statements) == 1
    assert principal.email == "reader@trove.example.test"


async def test_deleted_subject_is_blocked_from_normal_routes_but_can_retry_deletion(jwks, monkeypatch) -> None:
    jwks(key=_RSA_JWK)
    calls: list[bool] = []

    async def account_state(_sql: str, *_args: Any) -> dict[str, Any]:
        allow_deleted = bool(_args[3])
        calls.append(allow_deleted)
        return {
            "deleted": True,
            "deletion_pending": False,
            "id": None,
            "email": None,
            "display_name": None,
            "embeddings_enabled": False,
        }

    monkeypatch.setattr(auth, "fetchrow", account_state)
    request = _Request({"authorization": f"Bearer {_rs256_token()}"})

    with pytest.raises(ApiError) as raised:
        await auth.require_auth(request)
    assert raised.value.code == "account_deleted"

    principal = await auth.require_account_deletion_auth(request)
    assert principal.subject == "auth0|user-1"
    assert principal.id == ""
    assert calls == [False, True]


async def test_pending_deletion_blocks_normal_feature_routes(jwks, monkeypatch) -> None:
    jwks(key=_RSA_JWK)

    async def account_state(*_args: Any) -> dict[str, Any]:
        return {
            "deleted": False,
            "deletion_pending": True,
            "id": str(uuid.UUID(int=7)),
            "email": None,
            "display_name": None,
            "embeddings_enabled": False,
        }

    monkeypatch.setattr(auth, "fetchrow", account_state)
    with pytest.raises(ApiError) as raised:
        await auth.require_auth(_Request({"authorization": f"Bearer {_rs256_token()}"}))

    assert raised.value.status_code == 403
    assert raised.value.code == "account_deletion_pending"


async def test_require_auth_asks_for_a_bearer_token(install_config) -> None:
    install_config()
    for headers in ({}, {"authorization": "Token abc"}, {"authorization": "Bearer "}):
        with pytest.raises(ApiError) as raised:
            await auth.require_auth(_Request(headers))
        assert raised.value.status_code == 401
        assert raised.value.code == "unauthorized"


async def test_require_auth_reports_an_outage_as_503_so_the_client_keeps_its_token(jwks) -> None:
    jwks(error=jwt.PyJWKClientConnectionError("the provider is down"))
    with pytest.raises(ApiError) as raised:
        await auth.require_auth(_Request({"authorization": f"Bearer {_rs256_token()}"}))
    assert raised.value.status_code == 503


async def test_require_auth_reports_a_forged_token_as_401(jwks) -> None:
    jwks(key=_RSA_JWK)
    with pytest.raises(ApiError) as raised:
        await auth.require_auth(_Request({"authorization": "Bearer not-a-jwt"}))
    assert raised.value.status_code == 401
    assert raised.value.code == "invalid_token"


def test_the_jwks_client_is_built_with_arguments_pyjwt_accepts(install_config) -> None:
    """PyJWKClient takes no `algorithms` keyword; building it must not raise TypeError."""
    install_config()
    auth._jwks_client.cache_clear()
    try:
        assert isinstance(auth._jwks_client(), jwt.PyJWKClient)
    finally:
        auth._jwks_client.cache_clear()
