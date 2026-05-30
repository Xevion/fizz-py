"""Asyncio facade for fizzpy.

Mirrors the synchronous :class:`fizzpy.Client` but resolves operations on the
running event loop instead of blocking a thread. The underlying C++ core is the
same; only the resolve/reject bridge differs (see :mod:`fizzpy._transport`).

    import asyncio
    from fizzpy.aio import AsyncClient

    async def main():
        async with AsyncClient() as client:
            r = await client.get("https://www.cloudflare.com")
            print(r.status_code, r.tls)

    asyncio.run(main())
"""

from __future__ import annotations

from typing import Mapping, Optional

from . import _core
from ._common import (
    DEFAULT_ALPN,
    DEFAULT_GROUPS,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_TIMEOUT_MS,
    READ_DONE,
    TooManyRedirects,
    next_redirect,
    parse_url,
    strip_body_headers,
)
from ._http import Response, ResponseParser, build_request
from ._transport import run_async

__all__ = ["AsyncClient"]


class _Stale(Exception):
    """Internal: a pooled connection was dead; retry once on a fresh one."""


class AsyncClient:
    """An asyncio TLS HTTP client with per-host connection reuse.

    Idle connections are pooled and reused (HTTP/1.1 keep-alive); a connection
    found dead on reuse is replaced. Concurrent requests to the same host each
    take their own connection from the pool. Use as an async context manager (or
    call :meth:`aclose`) to close pooled connections.
    """

    def __init__(
        self,
        *,
        verify: bool = True,
        cafile: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_MS / 1000,
        alpn: Optional[list[str]] = None,
        groups: Optional[list] = None,
        follow_redirects: bool = True,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
    ) -> None:
        self._verify = verify
        self._cafile = cafile or ""
        self._timeout_ms = int(timeout * 1000)
        self._alpn = list(alpn) if alpn is not None else list(DEFAULT_ALPN)
        self._groups = list(groups) if groups is not None else list(DEFAULT_GROUPS)
        self._follow_redirects = follow_redirects
        self._max_redirects = max_redirects
        self._pool: dict[tuple[str, int], list] = {}

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        body: Optional[bytes] = None,
    ) -> Response:
        method = method.upper()
        seen = 0
        while True:
            response = await self._perform(method, url, headers=headers, body=body)
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

    async def _perform(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        body: Optional[bytes] = None,
    ) -> Response:
        target = parse_url(url)
        key = (target.host, target.port)
        raw = build_request(
            method, target.path, target.host, dict(headers) if headers else None, body
        )

        pooled = self._take(key)
        if pooled is not None:
            try:
                return await self._exchange(pooled, key, raw, reused=True)
            except _Stale:
                pooled.close()

        return await self._exchange(await self._connect(target), key, raw, reused=False)

    async def _connect(self, target):
        conn = _core.TlsConnection()
        await run_async(
            lambda resolve, reject: conn.connect(
                target.host,
                target.port,
                target.host,
                self._alpn,
                self._groups,
                self._verify,
                self._cafile,
                self._timeout_ms,
                resolve,
                reject,
            )
        )
        return conn

    async def _exchange(self, conn, key, raw: bytes, *, reused: bool) -> Response:
        try:
            await run_async(lambda resolve, reject: conn.write(raw, resolve, reject))
        except Exception as exc:
            if reused:
                raise _Stale from exc
            raise

        parser = ResponseParser()
        received = False
        while not parser.is_complete():
            try:
                chunk = await run_async(
                    lambda resolve, reject: conn.read(resolve, reject)
                )
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
            self._pool.setdefault(key, []).append(conn)
        else:
            conn.close()
        return response

    @staticmethod
    def _reusable(parser: ResponseParser, response: Response) -> bool:
        if parser.used_close_framing or response.http_version != "HTTP/1.1":
            return False
        return "close" not in (response.headers.get("Connection") or "").lower()

    def _take(self, key):
        conns = self._pool.get(key)
        return conns.pop() if conns else None

    async def aclose(self) -> None:
        """Close all pooled connections."""
        pooled = [c for conns in self._pool.values() for c in conns]
        self._pool.clear()
        for conn in pooled:
            conn.close()

    async def get(self, url: str, **kwargs) -> Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Response:
        return await self.request("POST", url, **kwargs)

    async def head(self, url: str, **kwargs) -> Response:
        return await self.request("HEAD", url, **kwargs)

    async def put(self, url: str, **kwargs) -> Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> Response:
        return await self.request("DELETE", url, **kwargs)

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
