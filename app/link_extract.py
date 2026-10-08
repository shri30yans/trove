"""Fetch public page metadata for saved links without letting a link reach internal services.

Every hostname is resolved up front, checked for a public address, and then the socket connects
straight to that pinned address, so a redirect or a re-resolving DNS record cannot point the
request at a private network.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from typing import cast
from urllib.parse import SplitResult, urljoin, urlsplit

import anyio
from bs4 import BeautifulSoup

MAX_PAGE_BYTES = 2_000_000
MAX_PAGE_TEXT = 50_000
MAX_REDIRECTS = 4
TIMEOUT_SECONDS = 8.0
USER_AGENT = "TroveLinkPreview/0.1 (+https://trove.app; public-page metadata requested by a user)"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".test")
_ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_DROP_SELECTORS = (
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "canvas",
    "nav",
    "footer",
    "header",
    "form",
    "button",
    "aside",
    '[aria-hidden="true"]',
)


class ExtractionError(ValueError):
    """The page could not be fetched or parsed."""


@dataclass(frozen=True)
class Page:
    title: str | None
    description: str | None
    text: str | None
    final_url: str


def _assert_public_address(address: str) -> str:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as error:
        raise ExtractionError("The website address is not public.") from error
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        raise ExtractionError("The website address is not public.")
    return str(ip)


def _validate(url: SplitResult) -> tuple[str, int, str]:
    if url.scheme not in ("http", "https"):
        raise ExtractionError("Unsupported URL protocol.")
    if url.username or url.password:
        raise ExtractionError("URLs with embedded credentials are not supported.")
    try:
        port = url.port
    except ValueError as error:
        raise ExtractionError("Non-standard website ports are not supported.") from error
    if port is None:
        port = 443 if url.scheme == "https" else 80
    if port not in (80, 443):
        raise ExtractionError("Non-standard website ports are not supported.")
    hostname = (url.hostname or "").strip("[]").lower()
    if not hostname or hostname == "localhost" or hostname.endswith(_BLOCKED_SUFFIXES):
        raise ExtractionError("The website address is not public.")
    return hostname, port, url.scheme


def _resolve(hostname: str, port: int) -> list[str]:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return [_assert_public_address(str(literal))]

    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ExtractionError("The website did not resolve to a usable address.") from error
    addresses = list({str(record[4][0]) for record in records})
    if not addresses or len(addresses) > 32:
        raise ExtractionError("The website did not resolve to a usable address.")
    return [_assert_public_address(address) for address in addresses]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """An HTTP(S) connection that dials a pre-validated address while naming the real host."""

    def __init__(self, hostname: str, port: int, addresses: list[str], scheme: str) -> None:
        self._addresses = addresses
        self._scheme = scheme
        super().__init__(hostname, port=port, timeout=TIMEOUT_SECONDS)
        # HTTPConnection derives the Host header from default_port, so without this an HTTPS
        # request would be sent as "Host: example.com:443".
        self.default_port = 443 if scheme == "https" else 80

    def connect(self) -> None:
        self.sock = self._open_socket()
        if self._scheme == "https":
            self.sock = self._ssl_context().wrap_socket(self.sock, server_hostname=self.host)

    def _open_socket(self) -> socket.socket:
        last_error: OSError | None = None
        for address in self._addresses:
            try:
                return socket.create_connection((address, self.port), timeout=TIMEOUT_SECONDS)
            except OSError as error:
                last_error = error
        raise ExtractionError("The website could not be reached.") from last_error

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        context = ssl.create_default_context()
        # SNI and certificate validation use the real hostname even though the socket is pinned.
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        return context


def _request_target(url: SplitResult) -> str:
    path = url.path or "/"
    return f"{path}?{url.query}" if url.query else path


def _read_bounded(response: http.client.HTTPResponse) -> bytes:
    declared = (response.getheader("content-length") or "").strip()
    if declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
        raise ExtractionError("Page is too large to extract.")
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = response.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_PAGE_BYTES:
            raise ExtractionError("Page is too large to extract.")
        chunks.append(chunk)
    return b"".join(chunks)


def _fetch(start_url: str) -> tuple[str, str, str]:
    current = urlsplit(start_url)._replace(fragment="")
    for _hop in range(MAX_REDIRECTS + 1):
        hostname, port, scheme = _validate(current)
        addresses = _resolve(hostname, port)
        connection = _PinnedHTTPConnection(hostname, port, addresses, scheme)
        try:
            connection.request(
                "GET",
                _request_target(current),
                headers={
                    "user-agent": USER_AGENT,
                    "accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                    "accept-encoding": "identity",
                },
            )
            response = connection.getresponse()
            if response.status in REDIRECT_STATUSES:
                location = response.getheader("location")
                response.read()
                if not location:
                    raise ExtractionError("The page redirected too many times.")
                current = urlsplit(urljoin(current.geturl(), location))._replace(fragment="")
                continue
            if not 200 <= response.status < 300:
                raise ExtractionError("The page did not return a successful response.")
            content_type = (response.getheader("content-type") or "").lower()
            if not any(token in content_type for token in _ALLOWED_CONTENT_TYPES):
                raise ExtractionError("The page content type is not supported.")
            body = _read_bounded(response).decode("utf-8", errors="replace")
            return body, content_type, current.geturl()
        except ExtractionError:
            raise
        except (http.client.HTTPException, OSError, ssl.SSLError) as error:
            raise ExtractionError("The page could not be fetched.") from error
        finally:
            connection.close()
    raise ExtractionError("Page redirect limit reached.")


def _meta(soup: BeautifulSoup, selector: str) -> str | None:
    tag = soup.select_one(selector)
    if tag is None:
        return None
    # "content" is not one of BeautifulSoup's multi-valued attributes, so the value is a plain str.
    return cast("str", tag.get("content") or "").strip() or None


def _body_text(soup: BeautifulSoup) -> str:
    for selector in ("article", '[role="main"]', "main"):
        found = soup.select_one(selector)
        text = found.get_text() if found else ""
        if text.strip():
            return text
    body = soup.body
    return body.get_text() if body else soup.get_text()


def _parse_html(body: str) -> tuple[str | None, str | None, str | None]:
    soup = BeautifulSoup(body, "lxml")
    title = (
        _meta(soup, 'meta[property="og:title"]')
        or _meta(soup, 'meta[name="twitter:title"]')
        or (soup.title.get_text().strip() if soup.title else None)
    )
    description = (
        _meta(soup, 'meta[property="og:description"]')
        or _meta(soup, 'meta[name="description"]')
        or _meta(soup, 'meta[name="twitter:description"]')
    )
    for tag in soup.select(",".join(_DROP_SELECTORS)):
        tag.decompose()
    text = " ".join(_body_text(soup).split())
    return (
        title[:500] if title else None,
        description[:4000] if description else None,
        text[:MAX_PAGE_TEXT] or None,
    )


def extract_public_page(raw_url: str) -> Page:
    body, content_type, final_url = _fetch(raw_url)
    if "text/plain" in content_type:
        return Page(title=None, description=None, text=body[:MAX_PAGE_TEXT] or None, final_url=final_url)
    title, description, text = _parse_html(body)
    return Page(title=title, description=description, text=text, final_url=final_url)


async def fetch_public_page(raw_url: str) -> Page | None:
    """Best-effort page metadata: a link that cannot be read is stored without enrichment."""
    try:
        return await anyio.to_thread.run_sync(extract_public_page, raw_url)
    except ExtractionError:
        return None
