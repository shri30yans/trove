"""Environment configuration for the Trove API, queue, and provider integrations.

Every integration Trove needs in order to serve a real request is a required field, in every
environment, so an incomplete configuration stops the process at import instead of surfacing later
as a runtime error. The only deliberate per-environment difference is `ENVIRONMENT_POLICIES`.

`VERTEX_*` fields stay optional because they gate the embedding capability, whose absent state is
reported actionably instead of stopping the boot. That is a feature, not a bypass. The fields are
grouped into one `VertexConfig` by `Config.vertex`, which is the only place that decides whether
Vertex exists; no caller re-derives it from individual keys.

A key is classified as a secret by one question only: does leaking it grant access? That decides
`SECRET_FIELDS`, which in turn decides whether the value is masked in reports and whether
`config.toml` may carry it. Everything that does not pass that test is configuration and belongs in
the checked-in profiles, so a checkout needs the fewest possible values in its environment.

Startup failures name configuration keys and the layer that supplied each value, never the values:
a crash log is readable to anyone with access to the deployment, and a credential printed there
stays compromised after the configuration is corrected.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import tomllib
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"
RUN_ENVIRONMENTS = ("local", "stage", "prod")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})
TOML_TABLES = frozenset({"defaults", "environments"})

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

REQUIRED_FIELDS = (
    "DATABASE_URL",
    "S3_ENDPOINT",
    "S3_REGION",
    "S3_BUCKET",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "CORS_ORIGIN",
    "PROXY_TRUSTED_IPS",
    "AUTH_JWKS_URL",
    "AUTH_ISSUER",
    "SUPABASE_URL",
    "SUPABASE_AUTH_API_KEY",
    "SUPABASE_SECRET_KEY",
    "MCP_PUBLIC_URL",
)

# A secret is a value that grants access once leaked, so it is never rendered and never committed.
# Secrets are also the values a deployment supplies from its own environment, so an inactive
# config.toml profile is judged on the shape of what it states rather than on whether it carries
# them. `SUPABASE_AUTH_API_KEY` is deliberately absent: Supabase issues it as the publishable key,
# it ships inside public client bundles by design, and it authorizes nothing a missing key would not
# already deny (see the check in `_checked_profile_urls` that keeps a real secret out of that field).
SECRET_FIELDS = frozenset(
    {
        "DATABASE_URL",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "SUPABASE_SECRET_KEY",
        "VERTEX_SERVICE_ACCOUNT_JSON_B64",
    }
)
URL_FIELDS = frozenset(
    {"DATABASE_URL", "S3_ENDPOINT", "SUPABASE_URL", "AUTH_JWKS_URL", "AUTH_ISSUER", "MCP_PUBLIC_URL"}
)
SOURCE_DEFAULTS = "config.toml [defaults]"
SOURCE_ENVIRONMENT = "the environment"
SOURCE_PORT = "the environment's PORT, which the platform assigns"
SOURCE_BUILTIN = "a built-in default"


def _profile_source(run_environment: str) -> str:
    return f"config.toml [environments.{run_environment}]"


def _layers_checked(run_environment: str) -> str:
    """Where the process looked for a key, in the order the layers are applied."""
    return f"{SOURCE_ENVIRONMENT}, {SOURCE_DEFAULTS} and {_profile_source(run_environment)}"


class EnvironmentPolicy(BaseModel, frozen=True):
    """The one place any per-environment difference is expressed."""

    allow_plain_http: bool
    allow_unpinned_cors: bool
    require_reachable_storage: bool
    dev_reloader: bool
    verbose_logging: bool


ENVIRONMENT_POLICIES: dict[Literal["local", "stage", "prod"], EnvironmentPolicy] = {
    "local": EnvironmentPolicy(
        allow_plain_http=True,
        allow_unpinned_cors=True,
        require_reachable_storage=False,
        dev_reloader=True,
        verbose_logging=True,
    ),
    "stage": EnvironmentPolicy(
        allow_plain_http=False,
        allow_unpinned_cors=False,
        require_reachable_storage=True,
        dev_reloader=False,
        verbose_logging=False,
    ),
    "prod": EnvironmentPolicy(
        allow_plain_http=False,
        allow_unpinned_cors=False,
        require_reachable_storage=True,
        dev_reloader=False,
        verbose_logging=False,
    ),
}


class VertexConfig(BaseModel, frozen=True):
    """One usable Vertex AI capability: what to call, where, and the credential that authorizes it.

    Only built when the group is complete, so the embedding service, its OAuth loader and the
    connectivity check all consume the same object instead of each answering "is Vertex configured"
    from raw keys. Absence is expressed once, as `Config.vertex` being None.
    """

    project_id: str
    location: str
    service_account_json_b64: str


class ConfigurationError(RuntimeError):
    """The process cannot start as configured. Safe to log: keys and layers, never values."""


def _is_unset(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _url_host(url: str) -> str:
    return urlparse(url).hostname or ""


def _is_loopback(url: str) -> bool:
    return _url_host(url) in LOOPBACK_HOSTS


def _checked_https_url(url: str, field: str, policy: EnvironmentPolicy) -> str:
    """Validate a URL that carries credentials or user data across the network."""
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError(f"{field} must be an absolute http(s) URL")
    if parsed.scheme == "http" and not (policy.allow_plain_http and _is_loopback(url)):
        raise ValueError(f"{field} must use HTTPS; plain HTTP is only allowed for a loopback address")
    return url


def _checked_database_url(url: str, policy: EnvironmentPolicy) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL supported by asyncpg")
    ssl_modes = parse_qs(parsed.query).get("sslmode", [])
    tls_configured = len(ssl_modes) == 1 and ssl_modes[0] in {"require", "verify-full"}
    if not tls_configured and not (policy.allow_plain_http and parsed.hostname in LOOPBACK_HOSTS):
        raise ValueError("DATABASE_URL must set sslmode=require unless Postgres runs on loopback")
    return url


def _checked_cors_origin(value: str, policy: EnvironmentPolicy) -> str:
    if value == "*":
        if not policy.allow_unpinned_cors:
            raise ValueError("CORS_ORIGIN must list allowed origins; * is only for RUN_ENV=local")
        return value
    for origin in value.split(","):
        parsed = urlparse(origin.strip())
        local_http = policy.allow_plain_http and parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS
        if (
            parsed.scheme != "https"
            and not local_http
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("CORS_ORIGIN must be * or a comma-separated list of https origins")
    return value


def _checked_proxy_trusted_ips(value: str) -> None:
    """Accept `*` or a list of addresses/CIDRs.

    Heroku's common runtime publishes no router-to-dyno address ranges and documents forwarded
    headers as untrusted, so `*` is the only value that yields a per-client address there. The rate
    limiter therefore keys authenticated traffic on the bearer token, not on this address; see
    app/middleware/rate_limit.py.
    """
    entries = [entry.strip() for entry in value.split(",")]
    if not all(entries):
        raise ValueError("PROXY_TRUSTED_IPS must contain one or more IP addresses or CIDRs")
    if "*" in entries:
        if entries != ["*"]:
            raise ValueError("PROXY_TRUSTED_IPS must be * on its own, or a list of addresses or CIDRs")
        return
    try:
        for entry in entries:
            ipaddress.ip_network(entry, strict=False)
    except ValueError as error:
        raise ValueError("PROXY_TRUSTED_IPS entries must be IP addresses or CIDRs") from error


def _checked_mcp_public_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path.rstrip("/") != "/mcp":
        raise ValueError("MCP_PUBLIC_URL must be the absolute MCP endpoint URL ending in /mcp")
    if parsed.query or parsed.fragment:
        raise ValueError("MCP_PUBLIC_URL must not include a query string or fragment")
    return value.rstrip("/")


def _jwt_role(token: str) -> str | None:
    """The `role` claim of a three-segment JWT, or None for any value that is not one.

    Reads only the payload and checks no signature: this classifies which Supabase key was
    configured, which is a configuration question, not an authorization decision.
    """
    segments = token.split(".")
    if len(segments) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(segments[1] + "=" * (-len(segments[1]) % 4)))
    except (ValueError, UnicodeDecodeError):
        return None
    role = payload.get("role") if isinstance(payload, dict) else None
    return role if isinstance(role, str) else None


def _checked_supabase_auth_keys(values: Mapping[str, Any]) -> None:
    """Keep the server-only key out of the field whose value is public by design.

    `SUPABASE_AUTH_API_KEY` is not classified as a secret, so nothing stops it being committed;
    rejecting a secret or service-role value by shape is what makes that safe. A legacy anon JWT and
    a service-role JWT are otherwise indistinguishable strings.
    """
    auth_key = values.get("SUPABASE_AUTH_API_KEY")
    secret_key = values.get("SUPABASE_SECRET_KEY")
    if isinstance(auth_key, str) and auth_key.strip():
        if auth_key.startswith("sb_secret_"):
            raise ValueError("SUPABASE_AUTH_API_KEY must be the publishable or legacy anon key, not a secret key")
        if _jwt_role(auth_key) == "service_role":
            raise ValueError("SUPABASE_AUTH_API_KEY must not be a service-role key")
    if auth_key and secret_key and auth_key == secret_key:
        raise ValueError("SUPABASE_AUTH_API_KEY and SUPABASE_SECRET_KEY must be different keys")


def _checked_profile_urls(values: Mapping[str, Any], policy: EnvironmentPolicy) -> None:
    """Apply the URL rules to whatever a profile actually states.

    Shared by the active `Config` and the sweep over inactive config.toml profiles, so one set of
    rules governs both and a mistyped staging endpoint fails at any startup rather than at its own.
    """
    for field in ("S3_ENDPOINT", "SUPABASE_URL", "MCP_PUBLIC_URL"):
        if values.get(field):
            _checked_https_url(str(values[field]), field, policy)
    if values.get("MCP_PUBLIC_URL"):
        _checked_mcp_public_url(str(values["MCP_PUBLIC_URL"]))
    if values.get("DATABASE_URL"):
        _checked_database_url(str(values["DATABASE_URL"]), policy)
    if values.get("CORS_ORIGIN"):
        _checked_cors_origin(str(values["CORS_ORIGIN"]), policy)
    if values.get("PROXY_TRUSTED_IPS"):
        _checked_proxy_trusted_ips(str(values["PROXY_TRUSTED_IPS"]))
    supabase_host = urlparse(str(values["SUPABASE_URL"])).netloc if values.get("SUPABASE_URL") else ""
    for field in ("AUTH_JWKS_URL", "AUTH_ISSUER"):
        if not values.get(field):
            continue
        url = str(values[field])
        if urlparse(url).scheme != "https":
            raise ValueError(f"{field} must use HTTPS")
        # A key set on another host would accept valid-looking strangers, but the comparison needs
        # both sides of it, which an inactive profile may not state.
        if supabase_host and urlparse(url).netloc != supabase_host:
            raise ValueError(f"{field} must point at the host configured as SUPABASE_URL")
    _checked_supabase_auth_keys(values)


class Config(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    RUN_ENV: Literal["local", "stage", "prod"]
    API_HOST: str = "0.0.0.0"
    API_PORT: int = Field(default=4000, ge=1, le=65535)
    CORS_ORIGIN: str
    PROXY_TRUSTED_IPS: str
    DATABASE_URL: str
    S3_ENDPOINT: str
    S3_REGION: str
    S3_BUCKET: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_FORCE_PATH_STYLE: bool = True
    MAX_UPLOAD_BYTES: int = Field(default=52_428_800, ge=1024)
    AUTH_AUDIENCE: str = "authenticated"
    AUTH_JWKS_URL: str
    AUTH_ISSUER: str
    SUPABASE_URL: str
    SUPABASE_AUTH_API_KEY: str
    SUPABASE_SECRET_KEY: str
    MCP_PUBLIC_URL: str
    VERTEX_SERVICE_ACCOUNT_JSON_B64: str | None = None
    VERTEX_PROJECT_ID: str | None = None
    VERTEX_LOCATION: str = "us"

    @property
    def policy(self) -> EnvironmentPolicy:
        return ENVIRONMENT_POLICIES[self.RUN_ENV]

    @property
    def cors_origins(self) -> list[str]:
        """The validated CORS_ORIGIN as the list CORSMiddleware expects."""
        if self.CORS_ORIGIN == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGIN.split(",") if origin.strip()]

    @property
    def vertex(self) -> VertexConfig | None:
        """The embedding capability, or None when this deployment does not configure it.

        A credential with no project, or a project with no credential, cannot produce a working
        client, so it is reported as absent rather than carried as a half-built object.
        """
        if self.VERTEX_SERVICE_ACCOUNT_JSON_B64 is None or self.VERTEX_PROJECT_ID is None:
            return None
        return VertexConfig(
            project_id=self.VERTEX_PROJECT_ID,
            location=self.VERTEX_LOCATION,
            service_account_json_b64=self.VERTEX_SERVICE_ACCOUNT_JSON_B64,
        )

    def __repr__(self) -> str:
        parts = (f"{name}={_display(name, getattr(self, name))}" for name in type(self).model_fields)
        return f"{type(self).__name__}({', '.join(parts)})"

    def __str__(self) -> str:
        return self.__repr__()

    @field_validator("VERTEX_SERVICE_ACCOUNT_JSON_B64", "VERTEX_PROJECT_ID", mode="before")
    @classmethod
    def _empty_capability_is_unset(cls, value: object) -> object:
        """Blank and whitespace-only capability values mean the same thing as absent ones.

        Uses the same test the required-field gate uses, so a key that cannot be a credential
        source never reaches `vertex` looking configured.
        """
        return None if _is_unset(value) else value

    @model_validator(mode="after")
    def _check_invariants(self) -> Config:
        missing = [name for name in REQUIRED_FIELDS if _is_unset(getattr(self, name))]
        if missing:
            raise ValueError(
                f"{', '.join(missing)} must be set for RUN_ENV={self.RUN_ENV}; "
                "Trove boots only with every integration configured"
            )
        _checked_profile_urls(self.model_dump(), self.policy)
        return self

    @field_validator("MCP_PUBLIC_URL")
    @classmethod
    def _check_mcp_public_url(cls, value: str) -> str:
        return _checked_mcp_public_url(value)


def _mask(value: str) -> str:
    return f"<set, {len(value)} chars>" if value else "<unset>"


def _redact_url(value: str) -> str:
    """Drop the user and password from a URL; the host is what an operator needs to see."""
    netloc = urlparse(value).netloc
    if not netloc or "@" not in netloc:
        return value
    return value.replace(netloc, netloc.rpartition("@")[2], 1)


def _display(name: str, value: Any) -> str:
    """One rendering rule shared by `Config.__repr__` and the operator report.

    A database URL is a credential, but its host and TLS mode are exactly what a misconfigured
    pooler failure calls for, so only its user and password are removed rather than the whole value.
    """
    if isinstance(value, str):
        if name in URL_FIELDS:
            return _redact_url(value)
        if name in SECRET_FIELDS:
            return _mask(value)
        return value
    return "" if value is None else str(value)


def _assigned_port() -> int | None:
    """The port the platform assigns, which overrides anything checked in.

    A non-numeric value is reported as the key it belongs to rather than as a bare int() failure,
    because the operator reading it needs to know which knob to turn.
    """
    assigned = os.environ.get("PORT", "").strip()
    if not assigned:
        return None
    try:
        return int(assigned)
    except ValueError:
        raise ConfigurationError(f"API_PORT is invalid: {SOURCE_PORT} is not a number") from None


def _as_bool(value: object) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise ValueError("S3_FORCE_PATH_STYLE must be true or false")
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    raise ValueError("S3_FORCE_PATH_STYLE must be true or false")


def _read_config_file() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("rb") as config_file:
            return tomllib.load(config_file)
    except FileNotFoundError as error:
        raise ConfigurationError(f"{CONFIG_PATH.name} is missing; it is a tracked file") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"{CONFIG_PATH.name} is not valid TOML: {error}") from error


def _layers(file_config: Mapping[str, Any], run_environment: str) -> list[tuple[str, Mapping[str, Any]]]:
    """The checked-in layers, weakest first: shared defaults, then this environment's profile."""
    defaults = file_config.get("defaults", {})
    profile = file_config.get("environments", {}).get(run_environment, {})
    return [(SOURCE_DEFAULTS, defaults), (_profile_source(run_environment), profile)]


def _check_every_profile(file_config: Mapping[str, Any]) -> None:
    """Validate every profile in config.toml, including the ones this process is not booting.

    An unknown key or a malformed URL in an inactive section is invisible until that environment
    deploys, which is the worst moment to discover it. A profile that has no section at all is
    legitimate: its environment may supply everything.
    """
    problems = [f"{CONFIG_PATH.name}: unknown table {name}" for name in sorted(set(file_config) - TOML_TABLES)]
    defaults = file_config.get("defaults", {})
    profiles = file_config.get("environments", {})
    if not isinstance(defaults, Mapping):
        raise ConfigurationError(f"{CONFIG_PATH.name}: defaults must be a table")
    if not isinstance(profiles, Mapping):
        raise ConfigurationError(f"{CONFIG_PATH.name}: environments must be a table")

    problems.extend(
        f"{CONFIG_PATH.name} {SOURCE_DEFAULTS}: {key} is a credential and belongs in the environment"
        for key in sorted(set(defaults) & SECRET_FIELDS)
    )
    problems.extend(
        f"{CONFIG_PATH.name}: unknown environment {name}; RUN_ENV must be one of {', '.join(RUN_ENVIRONMENTS)}"
        for name in sorted(set(profiles) - set(RUN_ENVIRONMENTS))
    )

    for name in sorted(set(profiles) & set(RUN_ENVIRONMENTS)):
        source = _profile_source(name)
        profile = profiles[name]
        if not isinstance(profile, Mapping):
            problems.append(f"{CONFIG_PATH.name} {source}: must be a table")
            continue
        problems.extend(
            f"{CONFIG_PATH.name} {source}: unknown key {key}" for key in sorted(set(profile) - CONFIG_FIELDS)
        )
        problems.extend(
            f"{CONFIG_PATH.name} {source}: {key} is a credential and belongs in the environment"
            for key in sorted(set(profile) & SECRET_FIELDS)
        )
        try:
            _checked_profile_urls({**defaults, **profile}, ENVIRONMENT_POLICIES[name])
        except ValueError as error:
            problems.append(f"{CONFIG_PATH.name} {source}: {error}")

    if problems:
        raise ConfigurationError("; ".join(problems))


def _merge_layers(file_config: Mapping[str, Any], run_environment: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Fold the layers into the values the model sees, remembering which layer supplied each one."""
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for source, layer in _layers(file_config, run_environment):
        for key, value in layer.items():
            values[key] = value
            sources[key] = source
    for key in sorted(CONFIG_FIELDS):
        if key in os.environ:
            values[key] = os.environ[key].strip()
            sources[key] = SOURCE_ENVIRONMENT
    values["RUN_ENV"] = run_environment
    sources["RUN_ENV"] = SOURCE_ENVIRONMENT
    # Heroku assigns the port, so its generated PORT overrides anything checked in.
    assigned_port = _assigned_port()
    if assigned_port is not None:
        values["API_PORT"] = assigned_port
        sources["API_PORT"] = SOURCE_PORT
    if "S3_FORCE_PATH_STYLE" in values:
        values["S3_FORCE_PATH_STYLE"] = _as_bool(values["S3_FORCE_PATH_STYLE"])
    return values, sources


def _provenance(values: Mapping[str, Any], run_environment: str) -> list[str]:
    """For each required key that no layer supplied, say where the process looked.

    Uses the same `_is_unset` test the model gate uses; this only chooses what to report.
    """
    lines = []
    for field in REQUIRED_FIELDS:
        if not _is_unset(values.get(field)):
            continue
        if field in SECRET_FIELDS:
            lines.append(f"{field} is not set; it must come from {SOURCE_ENVIRONMENT}")
        else:
            lines.append(f"{field} is not set; looked in {_layers_checked(run_environment)}")
    return lines


def _safe_failure_lines(error: ValidationError, sources: Mapping[str, str]) -> list[str]:
    """Render shape failures as key names and layers only.

    pydantic's own message embeds the rejected input values, so it is never surfaced.
    """
    lines = []
    for problem in error.errors():
        field = next((str(part) for part in problem["loc"]), "")
        detail = str(problem["msg"]).splitlines()[0].strip()
        source = sources.get(field)
        lines.append(f"{field or 'configuration'}: {detail}" + (f" (supplied by {source})" if source else ""))
    return lines


def _load() -> Config:
    run_environment = os.environ.get("RUN_ENV", "").strip()
    if run_environment not in ENVIRONMENT_POLICIES:
        raise ConfigurationError(
            f"RUN_ENV must be one of {', '.join(RUN_ENVIRONMENTS)}; "
            + (f"it is set to {run_environment}" if run_environment else "it is not set")
        )
    load_dotenv(f"{run_environment}.env", override=False)
    file_config = _read_config_file()
    _check_every_profile(file_config)
    values, sources = _merge_layers(file_config, run_environment)
    unfilled = _provenance(values, run_environment)
    if unfilled:
        raise ConfigurationError(
            f"Trove cannot start as configured for RUN_ENV={run_environment}: " + "; ".join(unfilled)
        )
    try:
        return Config.model_validate(values)
    except ValidationError as error:
        raise ConfigurationError(
            f"Trove cannot start as configured for RUN_ENV={run_environment}: "
            + "; ".join(_safe_failure_lines(error, sources))
        ) from None


def describe() -> list[dict[str, str]]:
    """One row per effective key: the key, the layer that supplied it, and its value safely shown."""
    config = get_config()
    _, sources = _merge_layers(_read_config_file(), config.RUN_ENV)
    rows = []
    for name in sorted(type(config).model_fields):
        rows.append(
            {
                "key": name,
                "source": sources.get(name, SOURCE_BUILTIN),
                "value": _display(name, getattr(config, name)),
            }
        )
    return rows


@lru_cache(maxsize=1)
def get_config() -> Config:
    return _load()


def main() -> None:
    """Print the effective configuration for operators: every key, its layer, its value masked."""
    print(json.dumps(describe(), indent=2))


if __name__ == "__main__":
    main()
