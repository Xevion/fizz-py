"""Shared request plumbing used by both the sync and async facades."""

from __future__ import annotations

from typing import NamedTuple, Optional
from urllib.parse import urljoin, urlsplit

from . import _core

DEFAULT_ALPN = ["http/1.1"]
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_MAX_REDIRECTS = 10
READ_DONE = b""

# Status codes that carry a Location and request a follow-up request.
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


class TooManyRedirects(Exception):
    """Raised when a request exceeds the client's redirect limit."""

# Offer the standardized post-quantum hybrid group first, with classical x25519
# as fallback — mirroring how Chrome/Firefox send both key shares by default.
# A server without ML-KEM support simply selects x25519 from our shares.
DEFAULT_GROUPS = [_core.NamedGroup.x25519_mlkem768, _core.NamedGroup.x25519]


class Target(NamedTuple):
    """A parsed request target: where to connect and what to ask for."""

    host: str
    port: int
    path: str


def next_redirect(
    method: str, url: str, status_code: int, location: Optional[str]
) -> Optional[tuple[str, str]]:
    """Resolve a redirect into the next ``(method, absolute_url)`` to request.

    Returns ``None`` when the response is not a redirect or carries no
    ``Location``. Method rewriting follows what browsers and ``requests`` do:
    303 forces a GET; 301/302 downgrade POST to GET; 307/308 preserve the
    original method (and the caller's body).
    """
    if status_code not in REDIRECT_CODES or not location:
        return None

    target = urljoin(url, location)
    method = method.upper()
    if status_code == 303 and method != "HEAD":
        method = "GET"
    elif status_code in (301, 302) and method == "POST":
        method = "GET"
    return method, target


def strip_body_headers(
    headers: Optional[dict],
) -> Optional[dict]:
    """Drop body-specific headers when a redirect downgrades a request to GET."""
    if not headers:
        return None
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("content-length", "content-type", "transfer-encoding")
    }


def parse_url(url: str) -> Target:
    """Split an ``https://`` URL into connection target + request path.

    Only TLS is supported — this is a TLS client. ``http://`` is rejected so a
    plaintext request can never silently happen.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ValueError(
            f"fizzpy only supports https:// URLs, got {parts.scheme!r}"
        )
    if not parts.hostname:
        raise ValueError(f"no host in URL: {url!r}")

    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    return Target(host=parts.hostname, port=parts.port or 443, path=path)
