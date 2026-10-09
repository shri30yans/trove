"""Configuration is a startup gate: every environment boots only with every integration configured,
every checked-in profile is validated even when it is not the one booting, and a startup failure
names keys and layers without ever naming a value.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from app import config as config_module
from app.config import (
    CONFIG_FIELDS,
    ENVIRONMENT_POLICIES,
    REQUIRED_FIELDS,
    SECRET_FIELDS,
    URL_FIELDS,
    ConfigurationError,
)
from tests.config_fixture import configured

RUN_ENVS = ("local", "stage", "prod")
SECRET_VALUES = {
    "DATABASE_URL": "postgresql://trove:sup3rsecret@pooler.example.test:5432/postgres?sslmode=require",
    "S3_ACCESS_KEY": "s3-access-leak-check",
    "S3_SECRET_KEY": "s3-secret-leak-check",
    "SUPABASE_AUTH_API_KEY": "publishable-leak-check",
    "SUPABASE_SECRET_KEY": "sb_secret_leak_check",
}


@pytest.mark.parametrize("run_env", RUN_ENVS)
def test_a_fully_configured_boot_passes_in_every_environment(run_env: str) -> None:
    assert run_env == configured(run_env).RUN_ENV


@pytest.mark.parametrize("run_env", RUN_ENVS)
@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_a_missing_integration_field_refuses_to_boot_in_every_environment(run_env: str, field: str) -> None:
    """Including RUN_ENV=local: an absent credential is a boot failure, not a runtime surprise."""
    for blank in ("", "   "):
        with pytest.raises(ValueError, match=field):
            configured(run_env, **{field: blank})


@pytest.mark.parametrize("run_env", RUN_ENVS)
def test_a_credential_bearing_url_never_accepts_plaintext(run_env: str) -> None:
    for field in ("SUPABASE_URL", "S3_ENDPOINT"):
        with pytest.raises(ValueError, match="HTTPS"):
            configured(run_env, **{field: "http://trove.example.test"})
    for field in ("AUTH_JWKS_URL", "AUTH_ISSUER"):
        with pytest.raises(ValueError, match=field):
            configured(run_env, **{field: "http://trove.example.test/auth/v1"})


def test_plaintext_is_allowed_only_on_loopback_and_only_locally() -> None:
    loopback = "http://localhost:4000/mcp"
    assert loopback == configured("local", MCP_PUBLIC_URL=loopback).MCP_PUBLIC_URL
    for run_env in RUN_ENVS:
        with pytest.raises(ValueError, match="loopback"):
            configured(run_env, MCP_PUBLIC_URL="http://api.example.test/mcp")
    with pytest.raises(ValueError, match="HTTPS"):
        configured("local", SUPABASE_URL="http://trove.example.test")
    with pytest.raises(ValueError, match="HTTPS"):
        configured("local", S3_ENDPOINT="http://storage.example.test/s3")


def test_loopback_postgres_may_skip_tls_but_a_remote_pooler_may_not() -> None:
    assert configured("local", DATABASE_URL="postgresql://u:p@127.0.0.1:5432/trove").DATABASE_URL
    for run_env in RUN_ENVS:
        with pytest.raises(ValueError, match="sslmode"):
            configured(run_env, DATABASE_URL="postgresql://u:p@pooler.example.test:5432/postgres")


def test_staging_holds_the_production_line_on_every_rule() -> None:
    assert ENVIRONMENT_POLICIES["stage"] == ENVIRONMENT_POLICIES["prod"]


def test_cors_wildcard_is_a_local_only_concession() -> None:
    assert configured("local", CORS_ORIGIN="*").CORS_ORIGIN == "*"
    for run_env in ("stage", "prod"):
        with pytest.raises(ValueError, match="CORS_ORIGIN"):
            configured(run_env, CORS_ORIGIN="*")
        with pytest.raises(ValueError, match="CORS_ORIGIN"):
            configured(run_env, CORS_ORIGIN="https://app.example.test/path")


def test_the_token_urls_must_be_the_configured_supabase_project() -> None:
    for field in ("AUTH_JWKS_URL", "AUTH_ISSUER"):
        with pytest.raises(ValueError, match=field):
            configured(**{field: "https://someone-elses-project.example.test/auth/v1"})


def test_the_publishable_and_secret_keys_must_differ() -> None:
    with pytest.raises(ValueError, match="different keys"):
        configured(SUPABASE_AUTH_API_KEY="same-key", SUPABASE_SECRET_KEY="same-key")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _supabase_jwt(role: str) -> str:
    """A signed-looking Supabase JWT carrying only the claim the classification reads."""
    header = _b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64url(json.dumps({"role": role}).encode())
    return f"{header}.{payload}.unsigned"


def test_the_publishable_field_accepts_either_public_key_shape() -> None:
    """A publishable key and a legacy anon key are the same authorization; both are configuration."""
    for key in ("sb_publishable_ABC123", _supabase_jwt("anon")):
        assert key == configured(SUPABASE_AUTH_API_KEY=key).SUPABASE_AUTH_API_KEY


def test_a_server_side_key_in_the_publishable_field_stops_the_boot() -> None:
    """The publishable field is not classified as a secret, so its shape is the only gate.

    A service-role key bypasses every row-level policy, and a new-format secret key is the same
    hazard, so pasting either one here must fail startup rather than silently widen access.
    """
    for key in ("sb_secret_ABC123", _supabase_jwt("service_role")):
        with pytest.raises(ValueError, match="SUPABASE_AUTH_API_KEY"):
            configured(SUPABASE_AUTH_API_KEY=key)


def test_the_mcp_url_must_be_the_endpoint_itself() -> None:
    for value in ("https://api.example.test", "https://api.example.test/mcp?debug=1", "not a url"):
        with pytest.raises(ValueError, match="MCP_PUBLIC_URL"):
            configured(MCP_PUBLIC_URL=value)


VERTEX_CREDENTIAL = "eyJ0ZXN0Ijp0cnVlfQ=="


def test_vertex_stays_an_optional_capability_flagged_absent_rather_than_blocking_boot() -> None:
    without_vertex = configured()
    assert without_vertex.VERTEX_PROJECT_ID is None
    assert without_vertex.VERTEX_SERVICE_ACCOUNT_JSON_B64 is None
    assert configured(VERTEX_PROJECT_ID="").VERTEX_PROJECT_ID is None
    assert without_vertex.vertex is None


def test_a_complete_vertex_group_builds_one_capability_object() -> None:
    vertex = configured(
        VERTEX_SERVICE_ACCOUNT_JSON_B64=VERTEX_CREDENTIAL,
        VERTEX_PROJECT_ID="gen-lang-client-0736864310",
    ).vertex
    assert vertex is not None
    assert vertex.project_id == "gen-lang-client-0736864310"
    assert vertex.location == "us"
    assert vertex.service_account_json_b64 == VERTEX_CREDENTIAL


@pytest.mark.parametrize(
    "half_configured",
    [
        {"VERTEX_PROJECT_ID": "gen-lang-client-0736864310"},
        {"VERTEX_SERVICE_ACCOUNT_JSON_B64": VERTEX_CREDENTIAL},
        {"VERTEX_PROJECT_ID": "gen-lang-client-0736864310", "VERTEX_SERVICE_ACCOUNT_JSON_B64": "  "},
    ],
)
def test_a_half_configured_vertex_group_is_absent_never_a_usable_looking_client(
    half_configured: dict[str, str],
) -> None:
    """A caller must not be able to build a client that will fail at the provider; the group is
    all-or-nothing, so a missing member means the capability reports itself absent."""
    assert configured(**half_configured).vertex is None


@pytest.mark.parametrize("run_env", RUN_ENVS)
def test_wildcard_proxy_trust_is_available_in_every_environment(run_env: str) -> None:
    """Heroku publishes no router address ranges, so a pinned CIDR is not an option in production."""
    assert configured(run_env, PROXY_TRUSTED_IPS="*").PROXY_TRUSTED_IPS == "*"


@pytest.mark.parametrize("value", ["10.0.0.0/8, *", "*, 10.0.0.0/8", " ", "10.0.0.0/8,not-an-address", "10.0.0.0/8,"])
def test_proxy_trust_must_be_a_wildcard_on_its_own_or_a_list_of_addresses(value: str) -> None:
    with pytest.raises(ValueError, match="PROXY_TRUSTED_IPS"):
        configured(PROXY_TRUSTED_IPS=value)


def test_an_operator_can_list_proxy_ranges_instead_of_the_wildcard() -> None:
    assert configured(PROXY_TRUSTED_IPS="10.0.0.0/8, 172.16.0.0/12").PROXY_TRUSTED_IPS


def test_the_config_repr_masks_every_credential_and_shows_the_public_key() -> None:
    """What grants access stays hidden; the publishable key shows, because showing it is the point.

    A startup failure still prints no value at all: this is the operator report, not the crash log.
    """
    config = configured(**SECRET_VALUES)
    for rendered in (repr(config), str(config)):
        for name, secret in SECRET_VALUES.items():
            if name in SECRET_FIELDS:
                assert secret not in rendered
            else:
                assert secret in rendered
        assert "sup3rsecret" not in rendered
        assert "trove@" not in rendered
    assert "pooler.example.test" in repr(config)


BASE_TOML = """
[defaults]
S3_ENDPOINT = "https://storage.example.test/s3"
S3_REGION = "ap-southeast-2"
S3_BUCKET = "trove-private"
SUPABASE_URL = "https://trove.example.test"
AUTH_JWKS_URL = "https://trove.example.test/auth/v1/.well-known/jwks.json"
AUTH_ISSUER = "https://trove.example.test/auth/v1"

[environments.stage]
CORS_ORIGIN = "https://app.example.test"
PROXY_TRUSTED_IPS = "10.0.0.0/8"
MCP_PUBLIC_URL = "https://api.example.test/mcp"
"""


def _boot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, toml_text: str, environment: dict[str, str]
) -> config_module.Config:
    """Load from a synthetic config.toml with only the named environment variables set.

    RUN_ENV=stage and an empty working directory keep the suite off the developer's own local.env,
    prod.env and config.toml, which are not what these tests are about.
    """
    config_file = tmp_path / "config.toml"
    config_file.write_text(toml_text, encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_file)
    monkeypatch.chdir(tmp_path)
    for name in [*CONFIG_FIELDS, "RUN_ENV", "PORT"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RUN_ENV", "stage")
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return config_module._load()


@pytest.fixture
def complete_deployment(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> config_module.Config:
    return _boot(monkeypatch, tmp_path, BASE_TOML, SECRET_VALUES)


def test_a_deployment_boots_from_the_checked_in_file_plus_its_secrets(complete_deployment: Any) -> None:
    assert complete_deployment.RUN_ENV == "stage"
    assert complete_deployment.S3_BUCKET == "trove-private"
    assert complete_deployment.API_PORT == 4000


def test_heroku_s_generated_port_overrides_the_checked_in_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    assert _boot(monkeypatch, tmp_path, BASE_TOML, {**SECRET_VALUES, "PORT": "1234"}).API_PORT == 1234


def test_an_unreadable_port_is_reported_as_the_layer_that_supplied_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    with pytest.raises(ConfigurationError, match="API_PORT"):
        _boot(monkeypatch, tmp_path, BASE_TOML, {**SECRET_VALUES, "PORT": "not-a-port"})


@pytest.mark.parametrize(
    ("section", "line"),
    [
        ("[defaults]", 'S3_Region = "ap-southeast-2"'),
        ("[environments.stage]", 'CORS_ORIGIN = "https://app.example.test"'),
        ("[environments.stage]", 'PROXY_TRUSTED_IPS = "10.0.0.0/8, *"'),
    ],
)
def test_a_mistake_in_the_checked_in_file_fails_startup_even_in_another_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, section: str, line: str
) -> None:
    """`stage` is the profile under test, but the same sweep covers the sections not being booted."""
    broken = BASE_TOML.replace(section, f"{section}\n{line}", 1)
    with pytest.raises(ConfigurationError, match="config.toml"):
        _boot(monkeypatch, tmp_path, broken, SECRET_VALUES)


def test_a_malformed_inactive_profile_fails_every_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Nobody boots `local` on the server, so its broken section must fail here instead."""
    toml_text = f'{BASE_TOML}\n[environments.local]\nCORS_ORIGIN = "http://app.example.test"\n'
    with pytest.raises(ConfigurationError, match="environments.local"):
        _boot(monkeypatch, tmp_path, toml_text, SECRET_VALUES)


def test_a_typo_in_an_environment_name_is_reported_not_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    toml_text = f'{BASE_TOML}\n[environments.pord]\nCORS_ORIGIN = "https://app.example.test"\n'
    with pytest.raises(ConfigurationError, match="pord"):
        _boot(monkeypatch, tmp_path, toml_text, SECRET_VALUES)


@pytest.mark.parametrize("field", sorted(SECRET_FIELDS))
def test_a_credential_committed_to_the_checked_in_file_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, field: str
) -> None:
    toml_text = BASE_TOML.replace("[environments.stage]", f'{field} = "committed-credential"\n\n[environments.stage]')
    with pytest.raises(ConfigurationError, match=f"{field} is a credential"):
        _boot(monkeypatch, tmp_path, toml_text, SECRET_VALUES)


def test_the_publishable_key_is_configuration_so_the_checked_in_file_may_supply_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The credential gate above must not sweep in a value that is public by design.

    Committing it is a per-project choice, so the file is judged on whether it carries a secret,
    and a publishable key in that field boots from the layer it was stated in.
    """
    toml_text = BASE_TOML.replace(
        "[environments.stage]", 'SUPABASE_AUTH_API_KEY = "sb_publishable_from_the_file"\n\n[environments.stage]'
    )
    environment = {name: value for name, value in SECRET_VALUES.items() if name != "SUPABASE_AUTH_API_KEY"}
    assert _boot(monkeypatch, tmp_path, toml_text, environment).SUPABASE_AUTH_API_KEY == "sb_publishable_from_the_file"


def test_a_server_side_key_committed_under_another_profile_still_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Nobody boots `local` on the server, so its publishable field must be checked here too."""
    toml_text = f'{BASE_TOML}\n[environments.local]\nSUPABASE_AUTH_API_KEY = "sb_secret_from_the_file"\n'
    with pytest.raises(ConfigurationError, match="environments.local"):
        _boot(monkeypatch, tmp_path, toml_text, SECRET_VALUES)


def test_a_missing_secret_names_its_key_and_where_to_set_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    environment = {name: value for name, value in SECRET_VALUES.items() if name != "SUPABASE_SECRET_KEY"}
    with pytest.raises(ConfigurationError) as failure:
        _boot(monkeypatch, tmp_path, BASE_TOML, environment)
    message = str(failure.value)
    assert "SUPABASE_SECRET_KEY is not set" in message
    assert "it must come from the environment" in message


def test_a_missing_public_key_reports_every_layer_that_was_searched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    toml_text = BASE_TOML.replace('MCP_PUBLIC_URL = "https://api.example.test/mcp"\n', "", 1)
    with pytest.raises(ConfigurationError) as failure:
        _boot(monkeypatch, tmp_path, toml_text, SECRET_VALUES)
    message = str(failure.value)
    assert "MCP_PUBLIC_URL is not set" in message
    assert "config.toml [defaults]" in message
    assert "config.toml [environments.stage]" in message


def test_a_startup_failure_never_prints_a_value(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """The crash log is the operator's only report, and it must be safe to paste into a ticket."""
    environment = {**SECRET_VALUES, "SUPABASE_URL_UNUSED": "x"}
    broken = BASE_TOML.replace(
        'SUPABASE_URL = "https://trove.example.test"', 'SUPABASE_URL = "https://trove.example.test:443/x"'
    )
    with pytest.raises(ConfigurationError) as failure:
        _boot(monkeypatch, tmp_path, broken, environment)
    message = str(failure.value)
    for secret in SECRET_VALUES.values():
        assert secret not in message
    assert "sup3rsecret" not in message


@pytest.fixture
def described(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> list[dict[str, str]]:
    config_module.get_config.cache_clear()
    try:
        _boot(monkeypatch, tmp_path, BASE_TOML, SECRET_VALUES)
        yield config_module.describe()
    finally:
        config_module.get_config.cache_clear()


def _row(rows: list[dict[str, str]], key: str) -> dict[str, str]:
    return next(row for row in rows if row["key"] == key)


def test_the_report_names_the_layer_behind_every_effective_key(described: list[dict[str, str]]) -> None:
    assert _row(described, "SUPABASE_URL")["source"] == "config.toml [defaults]"
    assert _row(described, "CORS_ORIGIN")["source"] == "config.toml [environments.stage]"
    assert _row(described, "S3_REGION")["source"] == "config.toml [defaults]"
    assert _row(described, "RUN_ENV")["source"] == "the environment"


def test_the_report_shows_a_secret_only_as_its_length(described: list[dict[str, str]]) -> None:
    for key in (SECRET_FIELDS - URL_FIELDS) & set(REQUIRED_FIELDS):
        row = _row(described, key)
        assert row["source"] == "the environment"
        assert row["value"].startswith("<set,")
        assert SECRET_VALUES[key] not in row["value"]


def test_the_report_redacts_the_password_inside_the_database_url(described: list[dict[str, str]]) -> None:
    value = _row(described, "DATABASE_URL")["value"]
    assert "sup3rsecret" not in value
    assert "trove@" not in value
    assert "pooler.example.test" in value


def test_the_report_marks_the_keys_no_layer_ever_stated(described: list[dict[str, str]]) -> None:
    assert _row(described, "API_PORT")["source"] == "a built-in default"
    assert _row(described, "VERTEX_PROJECT_ID")["source"] == "a built-in default"
