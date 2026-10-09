"""A complete synthetic configuration. A `Config` cannot be built from a partial one any more, so
tests start from every integration present and override only the field under test.

`COMPLETE_CONFIG` boots as `local`. `configured()` starts from the same values and applies the
shape a non-local deployment must have (HTTPS endpoints, pinned proxy, no wildcard CORS), so one
definition of a valid configuration serves the whole suite.
"""

from __future__ import annotations

from typing import Any, Literal

from app.config import Config

SUPABASE_HOST = "trove.example.test"

COMPLETE_CONFIG: dict[str, Any] = {
    "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/trove_test",
    "S3_ENDPOINT": "http://127.0.0.1:54321",
    "S3_REGION": "local",
    "S3_BUCKET": "trove-private",
    "S3_ACCESS_KEY": "test-access-key",
    "S3_SECRET_KEY": "test-secret-key",
    "CORS_ORIGIN": "*",
    "PROXY_TRUSTED_IPS": "*",
    "AUTH_JWKS_URL": f"https://{SUPABASE_HOST}/auth/v1/.well-known/jwks.json",
    "AUTH_ISSUER": f"https://{SUPABASE_HOST}/auth/v1",
    "SUPABASE_URL": f"https://{SUPABASE_HOST}",
    "SUPABASE_AUTH_API_KEY": "publishable-test-key",
    "SUPABASE_SECRET_KEY": "server-only-service-role-key",
    "MCP_PUBLIC_URL": "http://localhost:4000/mcp",
}

# The differences a real stage/prod deployment has from a laptop, expressed once.
DEPLOYED_SHAPE: dict[str, Any] = {
    "DATABASE_URL": "postgresql://u:p@pooler.example.test:5432/postgres?sslmode=require",
    "S3_ENDPOINT": "https://storage.example.test/s3",
    "CORS_ORIGIN": "https://app.example.test",
    "PROXY_TRUSTED_IPS": "10.0.0.0/8",
    "MCP_PUBLIC_URL": "https://api.example.test/mcp",
}


def synthetic_config(run_env: Literal["local", "stage", "prod"] = "local", **overrides: Any) -> Config:
    return Config.model_validate({"RUN_ENV": run_env, **COMPLETE_CONFIG, **overrides})


def configured(run_env: Literal["local", "stage", "prod"] = "prod", **overrides: Any) -> Config:
    return synthetic_config(run_env, **{**DEPLOYED_SHAPE, **overrides})
