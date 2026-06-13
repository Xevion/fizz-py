#!/usr/bin/env python3
"""Inject a custom ClientHello extension and prove it on the wire.

fizzpy exposes Fizz's ClientExtensions hook, so arbitrary extensions can be
appended to the TLS 1.3 ClientHello straight from Python. Here we add a
private-use extension carrying a marker string, then make an ordinary
post-quantum request: the handshake still negotiates X25519MLKEM768, and the
marker rides along in the ClientHello — turning "a post-quantum handshake" into
"*our* post-quantum handshake", identifiable on the wire.

    python examples/pq_marker.py

Capture the traffic in Wireshark, filter `tls.handshake.type == 1`, and expand
the ClientHello: you'll see the key_share for X25519MLKEM768 (group 0x11ec) and
an extension of type 65114 (0xFE5A) whose data is the marker bytes.
"""

import fizzpy

# 0xFE00-0xFEFF is the TLS "reserved for private use" range, safe for an
# experimental marker that won't collide with an IANA-registered extension type.
MARKER_TYPE = 0xFE5A
MARKER_DATA = b"hello from fizzpy"

URL = "https://blog.cloudflare.com"


def main() -> None:
    client = fizzpy.Client(extensions=[fizzpy.Extension(MARKER_TYPE, MARKER_DATA)])
    response = client.get(URL)
    tls = response.tls

    print(f"GET {URL} -> {response.status_code}")
    print(f"  group:  {tls['group']} (0x{tls['group_code']:04x})")
    print(f"  cipher: {tls['cipher']}")
    print(f"  marker: type 0x{MARKER_TYPE:04x} = {MARKER_DATA!r}")
    print()
    print("Capture in Wireshark (filter: tls.handshake.type == 1) to see the")
    print("marker extension alongside the X25519MLKEM768 key share.")


if __name__ == "__main__":
    main()
