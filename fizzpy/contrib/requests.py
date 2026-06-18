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

from typing import Any

from requests.adapters import HTTPAdapter

from fizzpy._tls import TlsConfig

from ._context import FizzSSLContext

__all__ = ["FizzAdapter"]


class FizzAdapter(HTTPAdapter):
    """A ``requests`` transport adapter that performs TLS via Fizz.

    Mount it for ``https://`` (and it composes with every other requests
    feature). Optionally pass a :class:`fizzpy.TlsConfig` to shape the handshake;
    all the usual ``HTTPAdapter`` keyword arguments (``max_retries``,
    ``pool_connections``, ...) are still accepted. ``fallback=True`` reaches
    TLS-1.2-only hosts over the stdlib ``ssl`` module (a classical, non
    post-quantum handshake) instead of failing on them.
    """

    def __init__(
        self,
        config: TlsConfig | None = None,
        *,
        fallback: bool = False,
        **kwargs: Any,
    ) -> None:
        # Set before super().__init__, which calls init_poolmanager during build.
        self._fizz_config = config
        # Opt-in: reach TLS-1.2-only hosts (which Fizz can't handshake) over the
        # stdlib ssl module — classical, non post-quantum. See FizzSSLContext.
        self._fallback = fallback
        super().__init__(**kwargs)

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        kwargs["ssl_context"] = FizzSSLContext(
            self._fizz_config, fallback=self._fallback
        )
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["ssl_context"] = FizzSSLContext(
            self._fizz_config, fallback=self._fallback
        )
        return super().proxy_manager_for(*args, **kwargs)
