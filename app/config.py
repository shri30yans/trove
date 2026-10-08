"""Environment configuration for the Trove API, queue, and provider integrations."""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

RUN_ENVIRONMENTS = ("local", "stage", "prod")
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"
CONFIG_FIELDS = {
    "API_HOST",
    "API_PORT",
    "CORS_ORIGIN",
    "PROXY_TRUSTED_IPS",
    "DATABASE_URL",
    "S3_ENDPOINT",
    "S3_REGION",
    "S3_BUCKET",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_FORCE_PATH_STYLE",
    "MAX_UPLOAD_BYTES",
    "VERTEX_SERVICE_ACCOUNT_JSON_B64",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "VERTEX_PROJECT_ID",
    "VERTEX_LOCATION",
    "AUTH_JWKS_URL",
    "AUTH_ISSUER",
    "AUTH_AUDIENCE",
    "SUPABASE_URL",
    "SUPABASE_AUTH_API_KEY",
    "SUPABASE_SECRET_KEY",
    "MCP_PUBLIC_URL",
}


def _get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


class Config(BaseModel):
    RUN_ENV: Literal["local", "stage", "prod"]
    API_HOST: str = "0.0.0.0"
    API_PORT: int = Field(default=4000, ge=1, le=65535)
    CORS_ORIGIN: str = ""
    PROXY_TRUSTED_IPS: str = "*"
    DATABASE_URL: str
    S3_ENDPOINT: str
    S3_REGION: str
    S3_BUCKET: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_FORCE_PATH_STYLE: bool = True
    MAX_UPLOAD_BYTES: int = Field(default=52_428_800, ge=1024)
    VERTEX_SERVICE_ACCOUNT_JSON_B64: str | None = None
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None
    VERTEX_PROJECT_ID: str | None = None
    VERTEX_LOCATION: str = "us"
    AUTH_JWKS_URL: str | None = None
    AUTH_ISSUER: str | None = None
    AUTH_AUDIENCE: str = "authenticated"
    SUPABASE_URL: str | None = None
    SUPABASE_AUTH_API_KEY: str | None = None
    SUPABASE_SECRET_KEY: str | None = None
    MCP_PUBLIC_URL: str = "http://localhost:4000/mcp"

    @field_validator("S3_FORCE_PATH_STYLE", mode="before")
    @classmethod
    def _blank_to_default(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("MCP_PUBLIC_URL")
    @classmethod
    def _check_mcp_public_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path.rstrip("/") != "/mcp":
            raise ValueError("MCP_PUBLIC_URL must be the absolute MCP endpoint URL ending in /mcp")
        if parsed.query or parsed.fragment:
            raise ValueError("MCP_PUBLIC_URL must not include a query string or fragment")
        return value.rstrip("/")

    @field_validator(
        "VERTEX_SERVICE_ACCOUNT_JSON_B64",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "VERTEX_PROJECT_ID",
        "AUTH_JWKS_URL",
        "AUTH_ISSUER",
        "SUPABASE_URL",
        "SUPABASE_AUTH_API_KEY",
        "SUPABASE_SECRET_KEY",
        mode="before",
    )
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def _check_runtime_invariants(self) -> Config:
        if not self.AUTH_JWKS_URL or not self.AUTH_ISSUER:
            raise ValueError("AUTH_JWKS_URL and AUTH_ISSUER are required in every environment")
        if self.RUN_ENV == "local":
            return self
        if not self.SUPABASE_URL or not self.SUPABASE_AUTH_API_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_AUTH_API_KEY are required outside RUN_ENV=local")
        if not self.SUPABASE_SECRET_KEY:
            raise ValueError("SUPABASE_SECRET_KEY is required outside RUN_ENV=local for account deletion")
        if not self.VERTEX_SERVICE_ACCOUNT_JSON_B64 and not self.GOOGLE_APPLICATION_CREDENTIALS:
            raise ValueError(
                "Vertex AI OAuth credentials are required outside RUN_ENV=local; configure "
                "VERTEX_SERVICE_ACCOUNT_JSON_B64 or GOOGLE_APPLICATION_CREDENTIALS"
            )
        if not self.VERTEX_PROJECT_ID:
            raise ValueError("VERTEX_PROJECT_ID is required outside RUN_ENV=local for Vertex AI embeddings")
        if not self.MCP_PUBLIC_URL.startswith("https://"):
            raise ValueError("MCP_PUBLIC_URL must use HTTPS outside RUN_ENV=local")
        if not self.SUPABASE_URL.startswith("https://"):
            raise ValueError("SUPABASE_URL must use HTTPS outside RUN_ENV=local")
        if "sslmode=require" not in self.DATABASE_URL and "sslmode=verify-full" not in self.DATABASE_URL:
            raise ValueError("DATABASE_URL must require TLS in production (sslmode=require)")
        if self.CORS_ORIGIN == "*" or not self.CORS_ORIGIN.strip():
            raise ValueError("CORS_ORIGIN must list allowed production origins")
        if not self.PROXY_TRUSTED_IPS.strip():
            raise ValueError("PROXY_TRUSTED_IPS must be configured")
        if not self.S3_ENDPOINT.startswith("https://"):
            raise ValueError("S3_ENDPOINT must use HTTPS outside RUN_ENV=local")
        return self


def _as_bool(value: object, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise ValueError(f"Expected true or false, got {value!r}")
    lowered = value.lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    raise ValueError(f"Expected true or false, got {value!r}")


def _load() -> Config:
    run_environment = _get("RUN_ENV")
    if run_environment not in RUN_ENVIRONMENTS:
        raise ValueError(f"Invalid environment configuration: RUN_ENV must be one of {', '.join(RUN_ENVIRONMENTS)}")
    load_dotenv(f"{run_environment}.env", override=False)
    with CONFIG_PATH.open("rb") as config_file:
        file_config = tomllib.load(config_file)
    values = dict(file_config.get("defaults", {}))
    values.update(file_config.get("environments", {}).get(run_environment, {}))
    values.update({name: os.environ[name].strip() for name in CONFIG_FIELDS if name in os.environ})
    is_local = run_environment == "local"
    values["RUN_ENV"] = run_environment
    values.setdefault("API_HOST", "0.0.0.0")
    values["API_PORT"] = int(_get("PORT") or str(values.get("API_PORT", 4000)))
    values.setdefault("CORS_ORIGIN", "*" if is_local else "")
    values.setdefault("PROXY_TRUSTED_IPS", "*" if is_local else "")
    values.setdefault("S3_FORCE_PATH_STYLE", True)
    values["S3_FORCE_PATH_STYLE"] = _as_bool(values["S3_FORCE_PATH_STYLE"], True)
    values.setdefault("MAX_UPLOAD_BYTES", 52_428_800)
    values.setdefault("VERTEX_LOCATION", "us")
    values.setdefault("AUTH_AUDIENCE", "authenticated")
    values.setdefault("MCP_PUBLIC_URL", "http://localhost:4000/mcp")
    return Config.model_validate(values)


@lru_cache(maxsize=1)
def get_config() -> Config:
    return _load()
