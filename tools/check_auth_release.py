#!/usr/bin/env python3
# ruff: noqa: T201
"""Safe, non-delivering smoke checks for a deployed Trove Auth API."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ProbeResult:
    status: int
    content_type: str
    body: bytes


def _request(base_url: str, method: str, path: str, body: bytes | None = None) -> ProbeResult:
    headers = {"Accept": "application/json, image/png"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    except (TimeoutError, URLError) as error:
        raise RuntimeError(f"request failed ({type(error).__name__})") from error
    with response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise RuntimeError("response exceeded the 2 MiB safety limit")
        return ProbeResult(
            status=response.status,
            content_type=response.headers.get_content_type(),
            body=data,
        )


def _error_code(result: ProbeResult) -> str | None:
    if result.content_type != "application/json":
        return None
    try:
        payload: Any = json.loads(result.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


def _base_url(value: str) -> str:
    parsed = urlsplit(value)
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (parsed.scheme != "https" and not local_http) or not parsed.netloc or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError(
            "API URL must use HTTPS (HTTP is allowed only on loopback) and contain no query or fragment"
        )
    return value.rstrip("/")


def run_checks(base_url: str) -> list[str]:
    failures: list[str] = []

    def check(name: str, method: str, path: str, expected_status: int, expected_type: str, expected: str) -> None:
        try:
            result = _request(base_url, method, path, b"{}" if method == "POST" else None)
        except RuntimeError as error:
            failures.append(f"{name}: {error}")
            print(f"FAIL {name}: request failed")
            return

        passed = result.status == expected_status and result.content_type == expected_type
        if expected == "live":
            try:
                passed = passed and json.loads(result.body) == {"status": "ok"}
            except (UnicodeDecodeError, json.JSONDecodeError):
                passed = False
        elif expected == "invalid_auth_request":
            passed = passed and _error_code(result) == expected
        elif expected == "png":
            passed = passed and result.body.startswith(b"\x89PNG\r\n\x1a\n")
        elif expected == "confirmation_landing":
            body = result.body.decode("utf-8", errors="replace")
            passed = passed and all(
                phrase in body for phrase in ("Email confirmed", "Open Trove", "access_token", "refresh_token")
            )

        print(f"{'PASS' if passed else 'FAIL'} {name}: HTTP {result.status} {result.content_type}")
        if not passed:
            failures.append(f"{name}: response did not match the expected contract")

    check("liveness", "GET", "/health/live", 200, "application/json", "live")
    for route in ("sign-up", "resend-confirmation", "confirm-email"):
        check(
            f"auth route {route}",
            "POST",
            f"/v1/auth/{route}",
            400,
            "application/json",
            "invalid_auth_request",
        )
    check(
        "email confirmation browser fallback",
        "GET",
        "/v1/auth/confirm-email",
        200,
        "text/html",
        "confirmation_landing",
    )
    check("email logo asset", "GET", "/brand/trove.png", 200, "image/png", "png")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("api_url", type=_base_url, help="Trove API origin, for example https://api.trove.zyphrlabs.com")
    args = parser.parse_args()
    failures = run_checks(args.api_url)
    if failures:
        print(f"Auth release check failed: {len(failures)} contract(s) are not live.", file=sys.stderr)
        return 1
    print("Auth release check passed. No email was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
