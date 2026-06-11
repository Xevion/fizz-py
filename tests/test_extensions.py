"""Custom ClientHello extension injection: validation + wire proof."""

import time

import pytest

import fizzpy
from _clienthello import parse_clienthello_extensions

MARKER_TYPE = 0xFE5A
MARKER_DATA = b"hello from fizzpy"


def test_managed_extension_rejected():
    # 0x0033 == key_share, which Fizz emits itself.
    with pytest.raises(ValueError, match="managed"):
        fizzpy.Client(extensions=[(0x0033, b"x")])


def test_duplicate_extension_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        fizzpy.Client(extensions=[(MARKER_TYPE, b"a"), (MARKER_TYPE, b"b")])


def test_extension_type_out_of_range():
    with pytest.raises(ValueError, match="range"):
        fizzpy.Client(extensions=[(0x10000, b"x")])


def test_extension_data_too_large():
    with pytest.raises(ValueError, match="65535"):
        fizzpy.Client(extensions=[(MARKER_TYPE, b"x" * 65536)])


def test_extension_namedtuple_accepted():
    # The Extension NamedTuple and a bare (int, bytes) tuple are interchangeable.
    client = fizzpy.Client(extensions=[fizzpy.Extension(MARKER_TYPE, MARKER_DATA)])
    assert client._extensions == [(MARKER_TYPE, MARKER_DATA)]


def test_injected_extension_appears_in_clienthello(raw_clienthello_server):
    client = fizzpy.Client(
        verify=False,
        extensions=[fizzpy.Extension(MARKER_TYPE, MARKER_DATA)],
    )
    # The server reads the ClientHello then drops the connection, so the
    # handshake necessarily fails — we only care about what went on the wire.
    with pytest.raises(Exception):
        client.get(raw_clienthello_server.url)

    record = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        record = raw_clienthello_server.clienthello
        if record:
            break
        time.sleep(0.02)
    assert record, "server captured no ClientHello"

    exts = parse_clienthello_extensions(record)
    assert MARKER_TYPE in exts, f"marker extension absent; saw {sorted(exts)}"
    assert exts[MARKER_TYPE] == MARKER_DATA
