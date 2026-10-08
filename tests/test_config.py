"""Production configuration invariants are a startup gate, not a runtime check."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Config

PROD_BASE: dict[str, Any] = {
    "RUN_ENV": "prod",
    "DATABASE_URL": "postgresql://u:p@pooler.example.test:5432/postgres?sslmode=require",
    "S3_ENDPOINT": "https://storage.example.test/s3",
    "S3_REGION": "local",
    "S3_BUCKET": "trove-private",
    "S3_ACCESS_KEY": "key",
    "S3_SECRET_KEY": "secret",
    "CORS_ORIGIN": "https://app.example.test",
    "PROXY_TRUSTED_IPS": "10.0.0.0/8",
    "AUTH_JWKS_URL": "https://auth.example.test/.well-known/jwks.json",
    "AUTH_ISSUER": "https://auth.example.test",
    "SUPABASE_URL": "https://project.example.test",
    "SUPABASE_AUTH_API_KEY": "publishable-test-key",
    "SUPABASE_SECRET_KEY": "server-only-test-key",
    "VERTEX_SERVICE_ACCOUNT_JSON_B64": "eyJ0ZXN0Ijp0cnVlfQ==",
    "VERTEX_PROJECT_ID": "gen-lang-client-0736864310",
    "MCP_PUBLIC_URL": "https://api.example.test/mcp",
}


def prod(**overrides: Any) -> Config:
    return Config.model_validate({**PROD_BASE, **overrides})


def test_a_fully_configured_production_boot_passes() -> None:
    assert prod().RUN_ENV == "prod"


def test_production_allows_trusting_every_forwarded_header_when_configured() -> None:
    assert prod(PROXY_TRUSTED_IPS="*").PROXY_TRUSTED_IPS == "*"
    for value in ("", "  "):
        with pytest.raises(ValueError, match="PROXY_TRUSTED_IPS"):
            prod(PROXY_TRUSTED_IPS=value)


def test_local_keeps_the_permissive_default() -> None:
    local = Config.model_validate(
        {
            "RUN_ENV": "local",
            "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/trove",
            "S3_ENDPOINT": "http://127.0.0.1:54321",
            "S3_REGION": "local",
            "S3_BUCKET": "trove-private",
            "S3_ACCESS_KEY": "key",
            "S3_SECRET_KEY": "secret",
            "AUTH_JWKS_URL": "https://auth.example.test/.well-known/jwks.json",
            "AUTH_ISSUER": "https://auth.example.test",
        }
    )
    assert local.PROXY_TRUSTED_IPS == "*"


def test_production_still_refuses_the_other_insecure_defaults() -> None:
    for field, value in (
        ("CORS_ORIGIN", "*"),
        ("DATABASE_URL", "postgresql://u:p@pooler.example.test:5432/postgres"),
        ("AUTH_JWKS_URL", ""),
        ("SUPABASE_AUTH_API_KEY", ""),
        ("SUPABASE_SECRET_KEY", ""),
        ("VERTEX_SERVICE_ACCOUNT_JSON_B64", ""),
        ("SUPABASE_URL", "http://project.example.test"),
        ("S3_ENDPOINT", "http://storage.example.test/s3"),
    ):
        with pytest.raises(ValueError):
            prod(**{field: value})


def test_local_auth_requires_the_provider_issuer_and_jwks() -> None:
    for field in ("AUTH_JWKS_URL", "AUTH_ISSUER"):
        with pytest.raises(ValueError, match="AUTH_JWKS_URL and AUTH_ISSUER"):
            Config.model_validate({**PROD_BASE, "RUN_ENV": "local", field: ""})
