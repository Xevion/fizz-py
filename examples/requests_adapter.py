#!/usr/bin/env python3
"""Keep requests, swap the TLS: post-quantum handshakes under a requests.Session.

This is fizzpy's headline use case. Mount :class:`FizzAdapter` for ``https://``
and requests keeps doing everything above TLS — cookies, redirects, retries,
connection pooling — while Fizz performs the handshake underneath, negotiating
the post-quantum X25519MLKEM768 group by default.

    pip install fizzpy[requests]
    python examples/requests_adapter.py

The negotiated TLS parameters are reachable through urllib3's connection object
(``r.raw.connection.sock``), which here is fizzpy's TlsSocket. The request uses
``stream=True`` so urllib3 keeps that connection attached instead of releasing it
back to the pool once the body is read.
"""

import requests

from fizzpy import NamedGroup, TlsConfig
from fizzpy.contrib.requests import FizzAdapter

URL = "https://www.cloudflare.com"


def main() -> None:
    session = requests.Session()
    # Force post-quantum only so the example fails loudly if ML-KEM is missing;
    # drop the config for the default [x25519_mlkem768, x25519] negotiation.
    config = TlsConfig(groups=[NamedGroup.x25519_mlkem768])
    session.mount("https://", FizzAdapter(config))

    with session.get(URL, stream=True) as response:
        tls = response.raw.connection.sock.tls

        print(f"GET {URL} -> {response.status_code}")
        print(f"  group:  {tls['group']} (0x{tls['group_code']:04x})")
        print(f"  cipher: {tls['cipher']}")
        print(f"  alpn:   {tls['alpn']}")
        print()
        print("requests handled HTTP; fizzpy handled the post-quantum handshake.")


if __name__ == "__main__":
    main()
