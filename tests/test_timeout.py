"""Read/write deadlines: a stalled peer must raise socket.timeout, not hang.

Before deadlines were enforced, a server that completed the handshake then went
silent would block the caller forever despite a configured timeout. These tests
pin that ``settimeout`` now bounds a ``recv`` (at the primitive and through both
adapters) and a ``sendall`` to an unresponsive peer, while leaving the
responsive happy path untouched.
"""

import socket
import time
from urllib.parse import urlsplit

import pytest

import fizzpy
from fizzpy import TlsConfig


def _connect(url: str) -> socket.socket:
    parts = urlsplit(url)
    return socket.create_connection((parts.hostname, parts.port))


def test_recv_times_out_on_stalled_peer(stalling_server):
    tcp = _connect(stalling_server.url)
    tls = fizzpy.wrap_socket(tcp, "localhost", TlsConfig(verify=False))
    try:
        tls.settimeout(0.5)
        tls.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        started = time.monotonic()
        with pytest.raises(socket.timeout):
            tls.recv(4096)
        elapsed = time.monotonic() - started
        # The deadline honoured the configured 0.5s: it fired (upper bound, so a
        # bug can't silently hang) but not instantly (lower bound, so a bug that
        # rejects immediately or mis-maps another error to timeout is caught).
        # The 0.3s floor tolerates scheduler jitter while still pinning intent.
        assert 0.3 < elapsed < 4
    finally:
        tls.close()
        tcp.close()


def test_sendall_times_out_on_unresponsive_peer(stalling_server):
    # The write-side deadline (setSendTimeout): a peer that completes the
    # handshake but never drains its receive window lets a large write fill the
    # kernel + TLS buffers and then stall. The send deadline must surface as
    # socket.timeout rather than hanging. 32 MiB comfortably exceeds any
    # autotuned loopback buffer, so the write cannot flush within 0.5s.
    tcp = _connect(stalling_server.url)
    tls = fizzpy.wrap_socket(tcp, "localhost", TlsConfig(verify=False))
    try:
        tls.settimeout(0.5)
        payload = b"x" * (32 * 1024 * 1024)
        started = time.monotonic()
        with pytest.raises(socket.timeout):
            tls.sendall(payload)
        elapsed = time.monotonic() - started
        assert 0.3 < elapsed < 8
    finally:
        tls.close()
        tcp.close()


def test_no_timeout_completes_normal_request(local_server):
    # A responsive server still round-trips with a generous deadline set — the
    # deadline plumbing must not break the happy path.
    tcp = _connect(local_server.url)
    tls = fizzpy.wrap_socket(tcp, "localhost", TlsConfig(verify=False))
    try:
        tls.settimeout(10)
        tls.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        raw = b""
        while True:
            chunk = tls.recv(4096)
            if not chunk:
                break
            raw += chunk
        assert raw.split(b"\r\n\r\n", 1)[1] == b"hello from local tls"
    finally:
        tls.close()
        tcp.close()


def test_requests_read_timeout_on_stalled_peer(stalling_server):
    requests = pytest.importorskip("requests")
    from fizzpy.contrib.requests import FizzAdapter

    session = requests.Session()
    session.mount("https://", FizzAdapter(TlsConfig(verify=False)))
    # timeout=(connect, read): the read deadline maps onto the TlsSocket and a
    # stalled response surfaces as requests' own ReadTimeout.
    with pytest.raises(requests.exceptions.ReadTimeout):
        session.get(stalling_server.url, verify=False, timeout=(5, 0.5))


def test_httpx_read_timeout_on_stalled_peer(stalling_server):
    httpx = pytest.importorskip("httpx")
    from fizzpy.contrib.httpx import FizzHTTPTransport

    transport = FizzHTTPTransport(TlsConfig(verify=False))
    with httpx.Client(transport=transport) as client:  # noqa: SIM117
        with pytest.raises(httpx.ReadTimeout):
            client.get(stalling_server.url, timeout=0.5)
