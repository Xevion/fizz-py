"""fizzpy — a low-level TLS 1.3 client toolkit built on Facebook's Fizz.

The synchronous facade lives here; the asyncio facade is :mod:`fizzpy.aio`.
Both drive the same C++ core, which runs every connection on a background
EventBase thread.

    import fizzpy

    r = fizzpy.get("https://www.cloudflare.com")
    print(r.status_code, r.headers["content-type"])
    print(r.tls)  # negotiated TLS 1.3 parameters

Certificate chains are verified against the system trust store by default.
Note: hostname (SAN) verification is not yet performed — see README.
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
from ._core import NamedGroup
from ._http import Headers, Response, ResponseParser, build_request
from ._transport import run_sync

__all__ = [
    "Client",
    "Response",
    "Headers",
    "NamedGroup",
    "request",
    "get",
    "post",
    "head",
    "put",
    "delete",
    "TlsParameters",
]

# Negotiated parameters are returned from the core as a plain dict; expose the
# key set as documentation.
TlsParameters = dict


class Client:
    """A synchronous TLS HTTP client.

    Each request currently opens a fresh TLS connection and closes it after the
    response (``Connection: close``); connection reuse is a future enhancement.
    """

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

    def request(
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
            run_sync(lambda resolve, reject: conn.write(raw, resolve, reject))

            parser = ResponseParser()
            while not parser.is_complete():
                chunk = run_sync(
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

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        return None


def request(method: str, url: str, **kwargs) -> Response:
    """One-shot request with a throwaway :class:`Client`."""
    verify = kwargs.pop("verify", True)
    cafile = kwargs.pop("cafile", None)
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT_MS / 1000)
    return Client(verify=verify, cafile=cafile, timeout=timeout).request(
        method, url, **kwargs
    )


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
