"""The pinned-socket link fetcher: its whole job is making sure a user's URL cannot reach inside
the network. These tests cover the validators and the parser, which is where that guarantee lives.
"""

from __future__ import annotations

import http.client
from urllib.parse import urlsplit

import pytest
from bs4 import BeautifulSoup

from app.link_extract import (
    MAX_PAGE_BYTES,
    MAX_PAGE_TEXT,
    ExtractionError,
    _assert_public_address,
    _meta,
    _parse_html,
    _read_bounded,
    _request_target,
    _resolve,
    _validate,
)

BLOCKED = (
    "127.0.0.1",
    "127.1.1.1",
    "10.0.0.5",
    "172.16.0.1",
    "192.168.1.1",
    "169.254.169.254",  # the cloud instance-metadata address
    "0.0.0.0",
    "::1",
    "fc00::1",
    "fe80::1",
    "224.0.0.1",
    "240.0.0.1",
    "::ffff:127.0.0.1",  # IPv4-mapped loopback
    "::ffff:169.254.169.254",
)
ALLOWED = ("93.184.216.34", "8.8.8.8", "2001:4860:4860::8888")


@pytest.mark.parametrize("address", BLOCKED)
def test_a_non_public_address_is_refused(address: str) -> None:
    with pytest.raises(ExtractionError, match="not public"):
        _assert_public_address(address)


@pytest.mark.parametrize("address", ALLOWED)
def test_a_public_address_is_returned_unchanged(address: str) -> None:
    assert _assert_public_address(address) == address


def test_an_ipv4_mapped_address_is_dialled_as_the_v4_it_stands_for() -> None:
    assert _assert_public_address("::ffff:93.184.216.34") == "93.184.216.34"


def test_a_literal_that_is_not_an_ip_is_refused() -> None:
    with pytest.raises(ExtractionError):
        _assert_public_address("example.com")
    with pytest.raises(ExtractionError):
        _assert_public_address("")


def _validate_url(url: str) -> tuple[str, int, str]:
    return _validate(urlsplit(url))


def test_only_http_and_https_are_allowed() -> None:
    for url in (
        "file:///etc/passwd",
        "gopher://example.com",
        "ftp://example.com",
        "http://example.com:25",
        "://missing",
    ):
        with pytest.raises(ExtractionError):
            _validate_url(url)


def test_credentials_in_a_url_are_refused() -> None:
    with pytest.raises(ExtractionError, match="credentials"):
        _validate_url("http://admin:password@example.com/")


def test_only_the_default_ports_survive() -> None:
    assert _validate_url("http://example.com/a") == ("example.com", 80, "http")
    assert _validate_url("https://example.com/a") == ("example.com", 443, "https")
    assert _validate_url("https://example.com:443/a") == ("example.com", 443, "https")
    for url in ("http://example.com:8080/a", "https://example.com:22/a", "http://example.com:0/a"):
        with pytest.raises(ExtractionError, match="ports"):
            _validate_url(url)


def test_internal_hostnames_are_refused_before_dns() -> None:
    for url in (
        "http://localhost/",
        "http://LOCALHOST:80/",
        "http://db.internal/",
        "http://printer.local/",
        "http://app.test/",
        "http://metadata.localhost/",
        "http:///no-host",
    ):
        with pytest.raises(ExtractionError, match="not public"):
            _validate_url(url)


def test_the_hostname_is_lowercased_and_ipv6_brackets_stripped() -> None:
    hostname, port, _ = _validate_url("https://Example.COM:443/path")
    assert (hostname, port) == ("example.com", 443)
    assert _validate_url("https://[::1]/")[0] == "::1"


def test_a_literal_ip_address_skips_resolution_and_is_still_checked() -> None:
    assert _resolve("93.184.216.34", 443) == ["93.184.216.34"]
    with pytest.raises(ExtractionError, match="not public"):
        _resolve("169.254.169.254", 80)


def test_an_unresolvable_host_reports_a_fetch_failure_not_a_crash() -> None:
    with pytest.raises(ExtractionError, match="resolve"):
        _resolve("this-host-really-does-not-exist.invalid", 443)


def test_the_request_target_keeps_the_query_and_defaults_to_root() -> None:
    assert _request_target(urlsplit("https://example.com/a/b?x=1&y=2")) == "/a/b?x=1&y=2"
    assert _request_target(urlsplit("https://example.com")) == "/"
    assert _request_target(urlsplit("https://example.com/?")) == "/"
    assert _request_target(urlsplit("https://example.com/a?x=%20")) == "/a?x=%20"


def test_the_fragment_never_reaches_the_server() -> None:
    assert _request_target(urlsplit("https://example.com/page#section")) == "/page"


class _Body(http.client.HTTPResponse):
    """A content-length plus a body that can be served in many chunks, or never declared."""

    def __init__(self, headers: dict[str, str], body: bytes) -> None:
        self._headers = headers
        self._body = body
        self._offset = 0

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name.lower(), default)

    def read(self, amount: int = -1) -> bytes:
        if amount is None or amount < 0:
            amount = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + amount]
        self._offset += len(chunk)
        return chunk


def test_a_declared_size_over_the_limit_is_refused_before_reading() -> None:
    response = _Body({"content-length": str(MAX_PAGE_BYTES + 1)}, b"")
    with pytest.raises(ExtractionError, match="too large"):
        _read_bounded(response)


def test_a_declared_size_that_is_not_a_number_is_ignored() -> None:
    assert _read_bounded(_Body({"content-length": "abc"}, b"hello")) == b"hello"


def test_an_undeclared_body_over_the_limit_is_stopped_while_streaming() -> None:
    oversized = b"x" * (MAX_PAGE_BYTES + 64 * 1024)
    with pytest.raises(ExtractionError, match="too large"):
        _read_bounded(_Body({}, oversized))


def test_a_body_exactly_at_the_limit_is_kept() -> None:
    exact = b"x" * MAX_PAGE_BYTES
    assert len(_read_bounded(_Body({}, exact))) == MAX_PAGE_BYTES


PAGE = """
<html><head>
  <title>Fallback Title</title>
  <meta name="description" content="html description">
  <meta property="og:title" content="Open Graph Title">
  <meta property="og:description" content="og description">
  <meta name="twitter:title" content="Twitter Title">
  <script>var tracking = "not prose";</script>
  <style>body { color: red }</style>
</head><body>
  <nav>Home About</nav>
  <header>Site header</header>
  <div>
    <h1>Real heading</h1>
    <p>First   paragraph
       with    whitespace.</p>
  </div>
  <footer>Copyright</footer>
</body></html>
"""


def test_open_graph_wins_over_twitter_and_the_title_tag() -> None:
    title, description, _ = _parse_html(PAGE)
    assert title == "Open Graph Title"
    assert description == "og description"


def test_twitter_metadata_is_the_second_choice() -> None:
    body = PAGE.replace('<meta property="og:title" content="Open Graph Title">', "")
    body = body.replace('<meta property="og:description" content="og description">', "")
    title, description, _ = _parse_html(body)
    assert title == "Twitter Title"
    assert description == "html description"


def test_the_document_title_is_the_last_resort() -> None:
    title, description, _ = _parse_html("<html><head><title>  Plain  </title></head><body><p>text</p></body></html>")
    assert title == "Plain"
    assert description is None


def test_boilerplate_nodes_are_dropped_from_the_extracted_text() -> None:
    _, _, text = _parse_html(PAGE)
    assert text is not None
    assert "Real heading" in text
    assert "First paragraph with whitespace." in text
    for noise in ("tracking", "color: red", "Home About", "Site header", "Copyright"):
        assert noise not in text


def test_whitespace_is_collapsed_and_the_text_is_capped() -> None:
    long_text = "<html><body><article>" + ("word " * (MAX_PAGE_TEXT + 10)) + "</article></body></html>"
    _, _, text = _parse_html(long_text)
    assert text is not None
    assert len(text) == MAX_PAGE_TEXT
    assert "  " not in text


def test_the_main_region_is_preferred_over_the_body() -> None:
    body = """<html><body><p>side noise</p><main><p>the article body</p></main></body></html>"""
    _, _, text = _parse_html(body)
    assert text == "the article body"


def test_a_page_with_no_metadata_or_body_yields_nones() -> None:
    assert _parse_html("<html></html>") == (None, None, None)


def test_a_title_longer_than_the_column_is_truncated() -> None:
    title, _, _ = _parse_html(f"<html><head><title>{'t' * 600}</title></head><body>x</body></html>")
    assert title is not None
    assert len(title) == 500


def test_meta_reads_content_and_treats_blank_as_absent() -> None:
    soup = BeautifulSoup('<meta name="x" content="   "><meta name="y" content="z">', "html.parser")
    assert _meta(soup, 'meta[name="x"]') is None
    assert _meta(soup, 'meta[name="y"]') == "z"
    assert _meta(soup, 'meta[name="missing"]') is None
