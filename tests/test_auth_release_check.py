from __future__ import annotations

from tools import check_auth_release


def test_safe_auth_release_probe_accepts_the_expected_live_contract(monkeypatch) -> None:
    requests: list[tuple[str, str, bytes | None]] = []

    def respond(_base_url: str, method: str, path: str, body: bytes | None = None) -> check_auth_release.ProbeResult:
        requests.append((method, path, body))
        if path == "/health/live":
            return check_auth_release.ProbeResult(200, "application/json", b'{"status":"ok"}')
        if path == "/brand/trove.png":
            return check_auth_release.ProbeResult(200, "image/png", b"\x89PNG\r\n\x1a\n")
        return check_auth_release.ProbeResult(
            400,
            "application/json",
            b'{"error":{"code":"invalid_auth_request","message":"Field required"}}',
        )

    monkeypatch.setattr(check_auth_release, "_request", respond)

    assert check_auth_release.run_checks("https://api.example.test") == []
    assert len(requests) == 5
    assert all(body == b"{}" for method, _path, body in requests if method == "POST")


def test_safe_auth_release_probe_identifies_a_missing_route_without_echoing_body(monkeypatch, capsys) -> None:
    def respond(_base_url: str, _method: str, path: str, _body: bytes | None = None) -> check_auth_release.ProbeResult:
        if path == "/health/live":
            return check_auth_release.ProbeResult(200, "application/json", b'{"status":"ok"}')
        if path == "/brand/trove.png":
            return check_auth_release.ProbeResult(200, "image/png", b"\x89PNG\r\n\x1a\n")
        if path.endswith("resend-confirmation"):
            return check_auth_release.ProbeResult(404, "text/plain", b"private provider detail")
        return check_auth_release.ProbeResult(
            400,
            "application/json",
            b'{"error":{"code":"invalid_auth_request"}}',
        )

    monkeypatch.setattr(check_auth_release, "_request", respond)

    failures = check_auth_release.run_checks("https://api.example.test")
    output = capsys.readouterr().out
    assert failures == ["auth route resend-confirmation: response did not match the expected contract"]
    assert "private provider detail" not in output
    assert "FAIL auth route resend-confirmation: HTTP 404 text/plain" in output
