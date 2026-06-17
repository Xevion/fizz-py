"""Use Fizz as the TLS layer under ``httpx`` — keep httpx, swap the TLS.

Construct a :class:`FizzHTTPTransport` and hand it to ``httpx.Client(transport=)``;
every HTTPS request the client makes then handshakes through Fizz (post-quantum
key exchange by default), while httpx keeps doing everything above TLS: cookies,
redirects, connection pooling, request/response models.

    import httpx
    from fizzpy.contrib.httpx import FizzHTTPTransport

    client = httpx.Client(transport=FizzHTTPTransport())
    r = client.get("https://www.cloudflare.com")
    print(r.status_code)

    # The negotiated handshake is on the TlsSocket, reachable via the network
    # stream while the response is open (use client.stream(...) to keep it open):
    with client.stream("GET", "https://www.cloudflare.com") as r:
        sock = r.extensions["network_stream"].get_extra_info("socket")
        print(sock.tls["group"])  # X25519MLKEM768

Shape the handshake with a :class:`fizzpy.TlsConfig`:

    from fizzpy import TlsConfig, NamedGroup
    pq_only = TlsConfig(groups=[NamedGroup.x25519_mlkem768])
    client = httpx.Client(transport=FizzHTTPTransport(pq_only))

Why TLS is configured via ``TlsConfig`` and not httpx's ``verify=``:
``httpx.HTTPTransport`` has no separate ``ssl_context`` parameter — the only way
to install a custom TLS implementation is through the ``verify=`` slot (httpx's
``create_ssl_context`` returns a non-bool/str value untouched). fizzpy *occupies*
that slot, so httpx's own ``verify=``/``cert=`` cannot also be honoured: they
would build a real OpenSSL context and evict fizzpy. ``FizzHTTPTransport`` rejects
them with a clear error rather than silently ignoring them. (This differs from the
``requests`` adapter, where ``HTTPAdapter(ssl_context=)`` is a *separate* channel
and urllib3 merges requests' ``verify=`` onto fizzpy's context.)

HTTP/1.1 only: httpcore decides the HTTP version from the ALPN it negotiates via
``ssl_object``, which a :class:`TlsSocket` does not expose, so an HTTP/2 handshake
could not be detected and driven safely. ``http2=True`` is therefore rejected.
"""

from __future__ import annotations

from typing import Any

import httpx

from fizzpy._tls import TlsConfig

from ._context import FizzSSLContext

__all__ = ["FizzHTTPTransport"]


class FizzHTTPTransport(httpx.HTTPTransport):
    """An ``httpx`` transport that performs TLS via Fizz.

    Pass it to ``httpx.Client(transport=...)``. Optionally pass a
    :class:`fizzpy.TlsConfig` to shape the handshake; the usual ``HTTPTransport``
    keyword arguments (``limits``, ``retries``, ``proxy``, ``trust_env``, ...) are
    still accepted. ``verify``/``cert``/``http2`` are not — see the module
    docstring for why.
    """

    def __init__(self, config: TlsConfig | None = None, **kwargs: Any) -> None:
        for unsupported in ("verify", "cert"):
            if unsupported in kwargs:
                raise TypeError(
                    f"FizzHTTPTransport does not accept {unsupported!r}; configure "
                    "TLS via FizzHTTPTransport(config=TlsConfig(...)). fizzpy owns "
                    "the verify= slot httpx uses for custom TLS contexts."
                )
        if kwargs.pop("http2", False):
            raise ValueError(
                "FizzHTTPTransport supports HTTP/1.1 only (a TlsSocket cannot "
                "surface ALPN to httpcore for HTTP/2 detection); pass http2=False."
            )
        # The duck-typed context rides in via verify=; httpx's create_ssl_context
        # returns it untouched and hands it to httpcore, which drives the handshake.
        # (verify wants ssl.SSLContext|str|bool; FizzSSLContext only quacks like one.)
        super().__init__(verify=FizzSSLContext(config), **kwargs)  # pyright: ignore[reportArgumentType]
