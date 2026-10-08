"""Test configuration.

app.config reads the environment at import time, so a hermetic local environment is pinned
here before any app module is imported. Tests never connect to a database: this suite covers
the pure layer only, and anything that needs Postgres is marked integration and skipped when
TROVE_INTEGRATION_DSN is absent.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

LOCAL_ENVIRONMENT = {
    "RUN_ENV": "local",
    "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:5432/trove_test",
    "S3_ENDPOINT": "http://127.0.0.1:54321",
    "S3_REGION": "local",
    "S3_BUCKET": "trove-private",
    "S3_ACCESS_KEY": "test",
    "S3_SECRET_KEY": "test",
    "AUTH_JWKS_URL": "https://auth.example.test/.well-known/jwks.json",
    "AUTH_ISSUER": "https://auth.example.test",
}

for name, value in LOCAL_ENVIRONMENT.items():
    os.environ[name] = value


@pytest.fixture
def mobile_schema():
    def run(module: str, name: str, payload: object) -> dict:
        result = subprocess.run(
            ["node", "tests/helpers/schema-cli.cjs", module, name],
            cwd=Path(__file__).resolve().parent.parent / "mobile",
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    return run
