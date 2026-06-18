"""Opt-in stdlib fallback for TLS-1.2-only hosts Fizz cannot handshake."""

import socket
import ssl
from urllib.parse import urlsplit

import pytest

from fizzpy import TlsConfig
from fizzpy.contrib._context import FizzSSLContext


def _connect(url: str) -> socket.socket:
    parts = urlsplit(url)
    return socket.create_connection((parts.hostname, parts.port))


def test_fizz_alone_cannot_handshake_tls12(tls12_server):
    # Without fallback, a TLS-1.2-only peer fails with an SSLError whose alert
    # names the version mismatch — the signal the fallback keys on.
    sock = _connect(tls12_server.url)
    try:
        with pytest.raises(ssl.SSLError) as excinfo:
            FizzSSLContext(TlsConfig(verify=False)).wrap_socket(sock, "127.0.0.1")
        assert "protocol_version" in str(excinfo.value)
    finally:
        sock.close()


def test_fallback_completes_tls12_handshake(tls12_server):
    # With fallback, the same peer is reached over stdlib ssl — a real
    # ssl.SSLSocket negotiating classical TLS 1.2 (no post-quantum).
    sock = _connect(tls12_server.url)
    ctx = FizzSSLContext(TlsConfig(verify=False), fallback=True)
    tls = ctx.wrap_socket(sock, "127.0.0.1")
    try:
        assert isinstance(tls, ssl.SSLSocket)
        assert tls.version() == "TLSv1.2"
    finally:
        tls.close()


def test_fallback_does_not_downgrade_on_cert_error(self_signed_server):
    # A TLS 1.3 server with an untrusted cert must still raise even with fallback
    # enabled — the fallback covers version mismatch only, never verification.
    url, _ = self_signed_server
    sock = _connect(url)
    try:
        with pytest.raises(ssl.SSLCertVerificationError):
            FizzSSLContext(TlsConfig(), fallback=True).wrap_socket(sock, "127.0.0.1")
    finally:
        sock.close()
