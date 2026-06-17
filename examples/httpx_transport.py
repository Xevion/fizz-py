#!/usr/bin/env python3
"""Keep httpx, swap the TLS: post-quantum handshakes under an httpx.Client.

Hand an httpx.Client a FizzHTTPTransport and httpx keeps doing everything above
TLS — cookies, redirects, connection pooling, its request/response models — while
Fizz performs the handshake underneath, negotiating X25519MLKEM768 by default.

    pip install fizzpy[httpx]
    python examples/httpx_transport.py

TLS is configured with a fizzpy.TlsConfig, not httpx's verify=: httpx exposes no
separate ssl_context parameter, so fizzpy occupies the verify= slot to install
itself (see fizzpy/contrib/httpx.py for the full reasoning).
"""

import httpx

from fizzpy import NamedGroup, TlsConfig
from fizzpy.contrib.httpx import FizzHTTPTransport

URL = "https://www.cloudflare.com"


def main() -> None:
    # Force post-quantum only so the example fails loudly if ML-KEM is missing;
    # drop the config for the default [x25519_mlkem768, x25519] negotiation.
    config = TlsConfig(groups=[NamedGroup.x25519_mlkem768])

    # stream=True keeps the network stream attached so the TlsSocket (and its
    # negotiated parameters) is reachable while the response is open.
    with (
        httpx.Client(transport=FizzHTTPTransport(config)) as client,
        client.stream("GET", URL) as response,
    ):
        sock = response.extensions["network_stream"].get_extra_info("socket")
        tls = sock.tls

        print(f"GET {URL} -> {response.status_code} ({response.http_version})")
        print(f"  group:  {tls['group']} (0x{tls['group_code']:04x})")
        print(f"  cipher: {tls['cipher']}")
        print(f"  alpn:   {tls['alpn']}")
        print()
        print("httpx handled HTTP; fizzpy handled the post-quantum handshake.")


if __name__ == "__main__":
    main()
