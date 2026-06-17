"""The wrap_socket primitive: a Fizz TLS handshake over a caller-owned socket."""

import socket
from urllib.parse import urlsplit

import pytest

import fizzpy
from fizzpy import TlsConfig


def _connect(url: str) -> socket.socket:
    parts = urlsplit(url)
    return socket.create_connection((parts.hostname, parts.port))


def _http_get(tls: fizzpy.TlsSocket, host: str, path: str = "/") -> bytes:
    """Drive a minimal HTTP/1.1 GET over the wrapped socket; return the body."""
    tls.sendall(
        f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
    )
    raw = b""
    while True:
        chunk = tls.recv(4096)
        if not chunk:
            break
        raw += chunk
    return raw.split(b"\r\n\r\n", 1)[1]


def test_wrap_socket_round_trips_over_self_signed(local_server):
    tcp = _connect(local_server.url)
    tls = fizzpy.wrap_socket(tcp, "localhost", TlsConfig(verify=False))
    try:
        assert tls.tls["version"] == "TLSv1.3"
        body = _http_get(tls, "localhost")
        assert body == b"hello from local tls"
    finally:
        tls.close()
        tcp.close()


def test_wrap_socket_exposes_negotiated_group(local_server):
    tcp = _connect(local_server.url)
    tls = fizzpy.wrap_socket(tcp, "localhost", TlsConfig(verify=False))
    try:
        params = tls.tls
        assert set(params) >= {"version", "cipher", "group", "group_code", "alpn"}
        # The default config offers the post-quantum group first; a stdlib
        # ssl server won't select it, so we just assert a group was negotiated.
        assert params["group"]
    finally:
        tls.close()
        tcp.close()


def test_wrap_socket_verifies_trusted_chain(ca_server):
    url, cafile, body = ca_server("localhost")
    tcp = _connect(url)
    tls = fizzpy.wrap_socket(tcp, "localhost", TlsConfig(cafile=cafile))
    try:
        assert _http_get(tls, "localhost") == body
    finally:
        tls.close()
        tcp.close()


def test_wrap_socket_rejects_wrong_hostname(ca_server):
    url, cafile, _ = ca_server("wrong.example")
    tcp = _connect(url)
    try:
        with pytest.raises(ConnectionError) as excinfo:
            fizzpy.wrap_socket(tcp, "localhost", TlsConfig(cafile=cafile))
        assert "hostname" in str(excinfo.value).lower()
    finally:
        tcp.close()


def test_wrap_socket_rejects_untrusted_chain(local_server):
    # Default config verifies against certifi, which does not trust the
    # server's self-signed cert.
    tcp = _connect(local_server.url)
    try:
        with pytest.raises(ConnectionError):
            fizzpy.wrap_socket(tcp, "localhost")
    finally:
        tcp.close()


def test_caller_may_close_original_socket_after_wrap(local_server):
    # wrap_socket dups the fd; the TLS connection lives on the dup, so closing
    # the caller's socket immediately must not disturb the handshake or I/O.
    tcp = _connect(local_server.url)
    tls = fizzpy.wrap_socket(tcp, "localhost", TlsConfig(verify=False))
    tcp.close()
    try:
        assert _http_get(tls, "localhost") == b"hello from local tls"
    finally:
        tls.close()
