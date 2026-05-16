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
    DEFAULT_TIMEOUT_MS,
    READ_DONE,
    parse_url,
)
from ._http import Response, ResponseParser, build_request
from ._transport import run_async

__all__ = ["AsyncClient"]


class AsyncClient:
    """An asyncio TLS HTTP client. One connection per request for now."""

    def __init__(
        self,
        *,
        verify: bool = True,
        cafile: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_MS / 1000,
        alpn: Optional[list[str]] = None,
        groups: Optional[list] = None,
    ) -> None:
        self._verify = verify
        self._cafile = cafile or ""
        self._timeout_ms = int(timeout * 1000)
        self._alpn = list(alpn) if alpn is not None else list(DEFAULT_ALPN)
        self._groups = list(groups) if groups is not None else list(DEFAULT_GROUPS)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        body: Optional[bytes] = None,
    ) -> Response:
        target = parse_url(url)
        conn = _core.TlsConnection()
        try:
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

            raw = build_request(
                method.upper(),
                target.path,
                target.host,
                dict(headers) if headers else None,
                body,
            )
            await run_async(lambda resolve, reject: conn.write(raw, resolve, reject))

            parser = ResponseParser()
            while not parser.is_complete():
                chunk = await run_async(
                    lambda resolve, reject: conn.read(resolve, reject)
                )
                if chunk == READ_DONE:
                    parser.feed_eof()
                    break
                parser.feed(chunk)

            response = parser.response
            if response is None:
                raise ConnectionError("connection closed before a full response")
            response.tls = conn.negotiated()
            return response
        finally:
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
        return None
