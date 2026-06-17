"""Use Fizz as the TLS layer under ``requests`` — keep requests, swap the TLS.

Mount :class:`FizzAdapter` on a ``requests.Session`` and every HTTPS request it
makes handshakes through Fizz (post-quantum key exchange by default), while
requests keeps doing everything above TLS: cookies, redirects, retries,
multipart, connection pooling.

    import requests
    from fizzpy.contrib.requests import FizzAdapter

    session = requests.Session()
    session.mount("https://", FizzAdapter())
    r = session.get("https://www.cloudflare.com")
    print(r.status_code)

    # The negotiated handshake is on the TlsSocket; stream=True keeps urllib3's
    # connection attached so it's reachable after the response is read.
    with session.get("https://www.cloudflare.com", stream=True) as r:
        print(r.raw.connection.sock.tls["group"])  # X25519MLKEM768

Pass a :class:`fizzpy.TlsConfig` to control the handshake (groups, ALPN, custom
ClientHello extensions, custom CA):

    from fizzpy import TlsConfig, NamedGroup
    pq_only = TlsConfig(groups=[NamedGroup.x25519_mlkem768])
    session.mount("https://", FizzAdapter(pq_only))

The adapter works by handing urllib3 a :class:`FizzSSLContext` that quacks like
``ssl.SSLContext`` but wraps sockets with Fizz instead of OpenSSL. urllib3 owns
the TCP connection and connection management; fizzpy owns only the handshake.
"""

# requests is an optional dependency and only partially typed (its HTTPAdapter
# base and urllib3 internals leak Unknown under strict mode); relax the rules that
# stem from that third-party boundary rather than scatter inline ignores.
# pyright: reportMissingModuleSource=false, reportUnknownMemberType=false
from __future__ import annotations

import ssl
from dataclasses import replace
from typing import Any

from requests.adapters import HTTPAdapter

from fizzpy._tls import TlsConfig, TlsSocket, wrap_socket

__all__ = ["FizzAdapter", "FizzSSLContext"]


class FizzSSLContext:
    """An ``ssl.SSLContext`` look-alike that wraps sockets with Fizz.

    Implements just the surface urllib3 drives: it accepts ``verify_mode`` /
    ``check_hostname`` assignments, records the CA file from
    ``load_verify_locations`` and the protocols from ``set_alpn_protocols``, and
    performs the handshake in :meth:`wrap_socket`. ``check_hostname`` defaults to
    ``True`` so urllib3 trusts fizzpy's in-handshake hostname check and skips its
    own ``getpeercert()`` matching (which a :class:`TlsSocket` does not provide).
    """

    def __init__(self, config: TlsConfig | None = None) -> None:
        self._config = config or TlsConfig()
        self._cafile = self._config.cafile
        self._alpn: list[str] = list(self._config.alpn)
        # urllib3 overwrites these from the request's verify settings.
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED

    def load_verify_locations(
        self,
        cafile: str | None = None,
        capath: str | None = None,
        cadata: str | bytes | None = None,
    ) -> None:
        if capath or cadata:
            raise NotImplementedError(
                "fizzpy trusts a single CA bundle file; capath/cadata are "
                "unsupported. Point requests at a cafile (verify='/path/ca.pem')."
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


class FizzAdapter(HTTPAdapter):
    """A ``requests`` transport adapter that performs TLS via Fizz.

    Mount it for ``https://`` (and it composes with every other requests
    feature). Optionally pass a :class:`fizzpy.TlsConfig` to shape the handshake;
    all the usual ``HTTPAdapter`` keyword arguments (``max_retries``,
    ``pool_connections``, ...) are still accepted.
    """

    def __init__(self, config: TlsConfig | None = None, **kwargs: Any) -> None:
        # Set before super().__init__, which calls init_poolmanager during build.
        self._fizz_config = config
        super().__init__(**kwargs)

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        kwargs["ssl_context"] = FizzSSLContext(self._fizz_config)
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["ssl_context"] = FizzSSLContext(self._fizz_config)
        return super().proxy_manager_for(*args, **kwargs)
