from starlette.requests import Request

from app.routes.mcp_oauth import _page, _valid_authorization_id


def test_authorization_ids_accept_uuid_and_opaque_url_safe_values() -> None:
    assert _valid_authorization_id("6f0e9de2-0b67-4c72-b3d5-973c0c1fb2ca")
    assert _valid_authorization_id("providerOpaque_0123~value")


def test_authorization_ids_reject_path_and_unbounded_values() -> None:
    assert _valid_authorization_id("../oauth/token") is None
    assert _valid_authorization_id("x" * 129) is None


def test_oauth_templates_escape_untrusted_text_and_disable_caching() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/oauth/consent",
            "headers": [],
            "query_string": b"",
            "server": ("api.trove.example.test", 443),
            "client": ("127.0.0.1", 1234),
        }
    )

    response = _page(
        request,
        "error.html",
        title="<script>bad()</script>",
        message="<img src=x onerror=bad()>",
    )

    body = response.body.decode()
    assert "<script>bad()" not in body
    assert "&lt;script&gt;bad()" in body
    assert "&lt;img src=x onerror=bad()&gt;" in body
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
