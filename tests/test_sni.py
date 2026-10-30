"""Server-name indication on the wire: sent for a hostname, omitted when empty."""

import socket
import ssl
import time
from urllib.parse import urlsplit

import pytest
from _clienthello import parse_clienthello_extensions

import fizzpy

SERVER_NAME = 0


def _clienthello_extensions(server, hostname: str) -> dict[int, bytes]:
    """Handshake toward the capture server and parse the ClientHello it saw."""
    port = urlsplit(server.url).port
    # The server drops the connection after reading the ClientHello.
    with (
        socket.create_connection(("127.0.0.1", port)) as sock,
        pytest.raises(ssl.SSLError),
    ):
        fizzpy.wrap_socket(sock, hostname, fizzpy.TlsConfig(verify=False))

    deadline = time.monotonic() + 5
    while not server.clienthello and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.clienthello, "server captured no ClientHello"
    return parse_clienthello_extensions(server.clienthello)


def test_hostname_is_sent_as_server_name(raw_clienthello_server):
    exts = _clienthello_extensions(raw_clienthello_server, "example.test")

    # server_name_list: length(2), type(1) = host_name, name length(2), name.
    assert exts[SERVER_NAME][5:] == b"example.test"


def test_empty_server_name_omits_the_extension(raw_clienthello_server):
    # RFC 6066 forbids IP literals as a server name, so callers pass "" for them.
    exts = _clienthello_extensions(raw_clienthello_server, "")

    assert SERVER_NAME not in exts
