"""Shared request plumbing used by both the sync and async facades."""

from __future__ import annotations

from typing import NamedTuple
from urllib.parse import urljoin, urlsplit

from . import _core

DEFAULT_ALPN = ["http/1.1"]
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_MAX_REDIRECTS = 10
READ_DONE = b""


def default_ca_file() -> str:
    """Path to the CA bundle used when a caller doesn't supply one.

    The extension bundles its own OpenSSL, whose compiled-in trust-store path
    doesn't exist on most hosts (and not at all in minimal images), so the
    OpenSSL default verifies nothing out of the box. certifi gives every
    install the Mozilla root set with no system setup. If certifi is somehow
    unavailable we return "" and fall back to OpenSSL's default store.
    """
    try:
        import certifi

        return certifi.where()
    except Exception:
        return ""


# Status codes that carry a Location and request a follow-up request.
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


class TooManyRedirects(Exception):
    """Raised when a request exceeds the client's redirect limit."""


# Offer the standardized post-quantum hybrid group first, with classical x25519
# as fallback — mirroring how Chrome/Firefox send both key shares by default.
# A server without ML-KEM support simply selects x25519 from our shares.
DEFAULT_GROUPS = [_core.NamedGroup.x25519_mlkem768, _core.NamedGroup.x25519]


class Extension(NamedTuple):
    """A custom TLS ClientHello extension: a type code and its opaque payload."""

    type: int
    data: bytes


# Extension types Fizz assembles into the ClientHello itself (from
# fizz/record/Types.h and the ClientHello build in ClientProtocol.cpp). Injecting
# any of these would duplicate or contradict Fizz's own, so they're refused.
FIZZ_MANAGED_EXTENSIONS = frozenset(
    {
        0,  # server_name
        10,  # supported_groups
        13,  # signature_algorithms
        16,  # application_layer_protocol_negotiation
        41,  # pre_shared_key
        42,  # early_data
        43,  # supported_versions
        44,  # cookie
        45,  # psk_key_exchange_modes
        47,  # certificate_authorities
        50,  # signature_algorithms_cert
        51,  # key_share
        0xFE0D,  # encrypted_client_hello
    }
)


def normalize_extensions(extensions) -> list[tuple[int, bytes]]:
    """Validate and coerce caller extensions to ``list[(int, bytes)]``.

    Accepts any iterable of ``(type, data)`` pairs (e.g. :class:`Extension`).
    Raises ``ValueError`` for an out-of-range type, oversized data, a Fizz-managed
    type, or a duplicate type — naming the offender.
    """
    if not extensions:
        return []
    out: list[tuple[int, bytes]] = []
    seen: set[int] = set()
    for item in extensions:
        etype, data = item
        etype = int(etype)
        if not 0 <= etype <= 0xFFFF:
            raise ValueError(f"extension type {etype} out of range 0..65535")
        data = bytes(data)
        if len(data) > 0xFFFF:
            raise ValueError(
                f"extension {etype} data is {len(data)} bytes; max is 65535"
            )
        if etype in FIZZ_MANAGED_EXTENSIONS:
            raise ValueError(
                f"extension type {etype} is managed by Fizz and cannot be injected"
            )
        if etype in seen:
            raise ValueError(f"duplicate extension type {etype}")
        seen.add(etype)
        out.append((etype, data))
    return out


class Target(NamedTuple):
    """A parsed request target: where to connect and what to ask for."""

    host: str
    port: int
    path: str


def next_redirect(
    method: str, url: str, status_code: int, location: str | None
) -> tuple[str, str] | None:
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
    if (status_code == 303 and method != "HEAD") or (
        status_code in (301, 302) and method == "POST"
    ):
        method = "GET"
    return method, target


def strip_body_headers(
    headers: dict | None,
) -> dict | None:
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
        raise ValueError(f"fizzpy only supports https:// URLs, got {parts.scheme!r}")
    if not parts.hostname:
        raise ValueError(f"no host in URL: {url!r}")

    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    return Target(host=parts.hostname, port=parts.port or 443, path=path)
