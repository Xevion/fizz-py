"""Minimal TLS ClientHello extension parser for tests.

Walks a raw handshake message (the bytes of a ``handshake(22)`` record's body,
starting at the ClientHello's handshake-type byte) and returns its extensions as
``{extension_type: extension_data}``. Pure stdlib — no TLS library — so the test
sees exactly what fizzpy put on the wire.
"""

from __future__ import annotations

import struct


def parse_clienthello_extensions(handshake: bytes) -> dict[int, bytes]:
    """Return ``{ext_type: ext_data}`` for a ClientHello handshake message."""
    p = 4  # handshake type(1) + length(3)
    p += 2  # client_version
    p += 32  # random
    sid_len = handshake[p]
    p += 1 + sid_len
    cs_len = struct.unpack(">H", handshake[p : p + 2])[0]
    p += 2 + cs_len
    comp_len = handshake[p]
    p += 1 + comp_len
    ext_total = struct.unpack(">H", handshake[p : p + 2])[0]
    p += 2
    end = p + ext_total

    exts: dict[int, bytes] = {}
    while p + 4 <= end:
        etype, elen = struct.unpack(">HH", handshake[p : p + 4])
        exts[etype] = handshake[p + 4 : p + 4 + elen]
        p += 4 + elen
    return exts
