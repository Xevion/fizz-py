"""A duck-typed ``ssl.SSLContext`` that wraps sockets with Fizz.

Shared by the contrib adapters. Both urllib3 (via ``requests``) and httpcore (via
``httpx``) drive a TLS handshake by calling a small, identical slice of the
``ssl.SSLContext`` API on whatever context they're given — ``set_alpn_protocols``
then ``wrap_socket`` — and neither does an ``isinstance(ctx, ssl.SSLContext)``
check on that path. So one duck-typed context serves both: it performs the
handshake with Fizz instead of OpenSSL and hands back a :class:`TlsSocket`.
"""

from __future__ import annotations

import ssl
from dataclasses import replace
from typing import Any

from fizzpy._tls import TlsConfig, TlsSocket, wrap_socket

__all__ = ["FizzSSLContext"]


class FizzSSLContext:
    """An ``ssl.SSLContext`` look-alike that wraps sockets with Fizz.

    Implements just the surface urllib3 and httpcore drive: it accepts
    ``verify_mode`` / ``check_hostname`` assignments, records the CA file from
    ``load_verify_locations`` and the protocols from ``set_alpn_protocols``, and
    performs the handshake in :meth:`wrap_socket`. ``check_hostname`` defaults to
    ``True`` so the caller trusts fizzpy's in-handshake hostname check and skips
    its own ``getpeercert()`` matching (which a :class:`TlsSocket` does not
    provide).

    ``verify_mode`` is seeded from the :class:`~fizzpy.TlsConfig`, so the context
    reflects the configured trust whether or not the HTTP client overwrites it.
    urllib3 *does* overwrite it (and calls ``load_verify_locations``) from
    ``requests``' per-request ``verify=``; httpcore does not, so for httpx the
    seeded value from the config is what takes effect.
    """

    def __init__(self, config: TlsConfig | None = None) -> None:
        self._config = config or TlsConfig()
        self._cafile = self._config.cafile
        self._alpn: list[str] = list(self._config.alpn)
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED if self._config.verify else ssl.CERT_NONE

    def load_verify_locations(
        self,
        cafile: str | None = None,
        capath: str | None = None,
        cadata: str | bytes | None = None,
    ) -> None:
        if capath or cadata:
            raise NotImplementedError(
                "fizzpy trusts a single CA bundle file; capath/cadata are "
                "unsupported. Point the client at a cafile instead."
            )
        if cafile:
            self._cafile = cafile

    def set_alpn_protocols(self, protocols: list[str]) -> None:
        self._alpn = list(protocols)

    def load_cert_chain(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "fizzpy does not support client certificates (mutual TLS) yet"
        )

    def wrap_socket(
        self, sock: Any, server_hostname: str | None = None, **_kwargs: object
    ) -> TlsSocket:
        config = replace(
            self._config,
            verify=self.verify_mode != ssl.CERT_NONE,
            cafile=self._cafile,
            alpn=self._alpn,
        )
        return wrap_socket(sock, server_hostname or "", config)
