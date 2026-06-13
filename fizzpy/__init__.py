"""fizzpy — a low-level TLS 1.3 client toolkit built on Facebook's Fizz.

The synchronous facade lives here; the asyncio facade is :mod:`fizzpy.aio`.
Both drive the same C++ core, which runs every connection on a background
EventBase thread.

    import fizzpy

    r = fizzpy.get("https://www.cloudflare.com")
    print(r.status_code, r.headers["content-type"])
    print(r.tls)  # negotiated TLS 1.3 parameters

Certificate chains are verified against the system trust store and the
hostname is checked against the certificate's SAN by default.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping

from . import _core
from ._common import (
    DEFAULT_ALPN,
    DEFAULT_GROUPS,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_TIMEOUT_MS,
    READ_DONE,
    Extension,
    TooManyRedirects,
    default_ca_file,
    next_redirect,
    normalize_extensions,
    parse_url,
    strip_body_headers,
)
from ._core import NamedGroup
from ._http import Headers, Response, ResponseParser, build_request
from ._transport import run_sync

__all__ = [
    "Client",
    "Extension",
    "Headers",
    "NamedGroup",
    "Response",
    "TlsParameters",
    "TooManyRedirects",
    "delete",
    "get",
    "head",
    "post",
    "put",
    "request",
]

# Negotiated parameters are returned from the core as a plain dict; expose the
# key set as documentation.
TlsParameters = dict


class _Stale(Exception):
    """Internal: a pooled connection was dead; retry once on a fresh one."""


class Client:
    """A synchronous TLS HTTP client.

    Idle connections are kept in a per-host pool and reused (HTTP/1.1
    keep-alive). A pooled connection found dead on reuse is transparently
    replaced for idempotent retries. Call :meth:`close` (or use the client as a
    context manager) to close pooled connections.
    """

    def __init__(
        self,
        *,
        verify: bool = True,
        cafile: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_MS / 1000,
        alpn: list[str] | None = None,
        groups: list | None = None,
        extensions: list | None = None,
        follow_redirects: bool = True,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
    ) -> None:
        self._verify = verify
        self._cafile = cafile or default_ca_file()
        self._timeout_ms = int(timeout * 1000)
        self._alpn = list(alpn) if alpn is not None else list(DEFAULT_ALPN)
        self._groups = list(groups) if groups is not None else list(DEFAULT_GROUPS)
        self._extensions = normalize_extensions(extensions)
        self._follow_redirects = follow_redirects
        self._max_redirects = max_redirects
        self._pool: dict[tuple[str, int], list] = {}
        self._lock = threading.Lock()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        method = method.upper()
        seen = 0
        while True:
            response = self._perform(method, url, headers=headers, body=body)
            response.url = url
            nxt = (
                next_redirect(
                    method, url, response.status_code, response.headers.get("Location")
                )
                if self._follow_redirects
                else None
            )
            if nxt is None:
                return response
            if seen >= self._max_redirects:
                raise TooManyRedirects(
                    f"exceeded {self._max_redirects} redirects (last: {url})"
                )
            new_method, url = nxt
            if new_method != method:
                method, body, headers = new_method, None, strip_body_headers(headers)
            seen += 1

    def _perform(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        target = parse_url(url)
        key = (target.host, target.port)
        raw = build_request(
            method, target.path, target.host, dict(headers) if headers else None, body
        )

        pooled = self._take(key)
        if pooled is not None:
            try:
                return self._exchange(pooled, key, raw, reused=True)
            except _Stale:
                pooled.close()  # dead idle connection; fall through to a fresh one

        return self._exchange(self._connect(target), key, raw, reused=False)

    def _connect(self, target) -> _core.TlsConnection:
        conn = _core.TlsConnection()
        run_sync(
            lambda resolve, reject: conn.connect(
                target.host,
                target.port,
                target.host,
                self._alpn,
                self._groups,
                self._verify,
                self._cafile,
                self._timeout_ms,
                self._extensions,
                resolve,
                reject,
            )
        )
        return conn

    def _exchange(self, conn, key, raw: bytes, *, reused: bool) -> Response:
        try:
            run_sync(lambda resolve, reject: conn.write(raw, resolve, reject))
        except Exception as exc:
            # A reused connection that fails before the request lands was closed
            # by the server while idle — safe to retry on a fresh one.
            if reused:
                raise _Stale from exc
            raise

        parser = ResponseParser()
        received = False
        while not parser.is_complete():
            try:
                chunk = run_sync(lambda resolve, reject: conn.read(resolve, reject))
            except Exception as exc:
                if reused and not received:
                    raise _Stale from exc
                raise
            if chunk == READ_DONE:
                if reused and not received:
                    raise _Stale
                parser.feed_eof()
                break
            received = True
            parser.feed(chunk)

        response = parser.response
        if response is None:
            if reused:
                raise _Stale
            raise ConnectionError("connection closed before a full response")
        response.tls = conn.negotiated()

        if self._reusable(parser, response):
            self._give(key, conn)
        else:
            conn.close()
        return response

    @staticmethod
    def _reusable(parser: ResponseParser, response: Response) -> bool:
        if parser.used_close_framing or response.http_version != "HTTP/1.1":
            return False
        return "close" not in (response.headers.get("Connection") or "").lower()

    def _take(self, key):
        with self._lock:
            conns = self._pool.get(key)
            return conns.pop() if conns else None

    def _give(self, key, conn) -> None:
        with self._lock:
            self._pool.setdefault(key, []).append(conn)

    def close(self) -> None:
        """Close all pooled connections."""
        with self._lock:
            pooled = [c for conns in self._pool.values() for c in conns]
            self._pool.clear()
        for conn in pooled:
            conn.close()

    def get(self, url: str, **kwargs) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Response:
        return self.request("POST", url, **kwargs)

    def head(self, url: str, **kwargs) -> Response:
        return self.request("HEAD", url, **kwargs)

    def put(self, url: str, **kwargs) -> Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> Response:
        return self.request("DELETE", url, **kwargs)

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


_CLIENT_KWARGS = frozenset(
    {
        "verify",
        "cafile",
        "timeout",
        "alpn",
        "groups",
        "extensions",
        "follow_redirects",
        "max_redirects",
    }
)


def request(method: str, url: str, **kwargs) -> Response:
    """One-shot request with a throwaway :class:`Client`."""
    client_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in _CLIENT_KWARGS}
    return Client(**client_kwargs).request(method, url, **kwargs)


def get(url: str, **kwargs) -> Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> Response:
    return request("POST", url, **kwargs)


def head(url: str, **kwargs) -> Response:
    return request("HEAD", url, **kwargs)


def put(url: str, **kwargs) -> Response:
    return request("PUT", url, **kwargs)


def delete(url: str, **kwargs) -> Response:
    return request("DELETE", url, **kwargs)
