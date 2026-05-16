"""Shared request plumbing used by both the sync and async facades."""

from __future__ import annotations

from typing import NamedTuple
from urllib.parse import urlsplit

DEFAULT_ALPN = ["http/1.1"]
DEFAULT_TIMEOUT_MS = 30_000
READ_DONE = b""


class Target(NamedTuple):
    """A parsed request target: where to connect and what to ask for."""

    host: str
    port: int
    path: str


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
