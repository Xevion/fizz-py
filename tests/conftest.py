"""Shared test fixtures, including local TLS 1.3 servers with controlled certs.

Certificate behaviour can't be tested against public endpoints: hosts with bad
certs (e.g. badssl.com) are usually TLS 1.2 only, and Fizz is TLS 1.3 only, so
the handshake fails for the wrong reason. Local servers with freshly minted
certs give deterministic, offline targets:

- ``self_signed_server`` — an untrusted self-signed cert (tests chain rejection).
- ``ca_server`` — a factory minting a private CA and a leaf cert with a chosen
  SAN, so hostname matching can be tested with a *trusted* chain (the CA is
  passed to the client via ``cafile``), isolating the hostname check.
"""

import http.server
import socket
import ssl
import subprocess
import threading

import pytest

BODY = b"hello from local tls"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _DualStackServer(http.server.HTTPServer):
    # "localhost" may resolve to ::1 or 127.0.0.1 depending on the resolver;
    # bind a dual-stack IPv6 socket so the client reaches us either way.
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def _serve_tls(cert: str, key: str):
    """Start a dual-stack TLS 1.3 HTTP server; return (httpd, thread, port)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(BODY)))
            self.end_headers()
            self.wfile.write(BODY)

        def log_message(self, *args):
            pass

    port = _free_port()
    httpd = _DualStackServer(("::", port), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(cert, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, port


def _openssl(*args: str) -> None:
    subprocess.run(["openssl", *args], check=True, capture_output=True)


@pytest.fixture(scope="session")
def self_signed_server(tmp_path_factory):
    """Yield ``(url, body)`` for a server using an untrusted self-signed cert."""
    d = tmp_path_factory.mktemp("selfsigned")
    cert, key = str(d / "cert.pem"), str(d / "key.pem")
    _openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-keyout", key, "-out", cert,
        "-days", "1", "-nodes", "-subj", "/CN=localhost",
    )
    httpd, thread, port = _serve_tls(cert, key)
    try:
        yield f"https://127.0.0.1:{port}/", BODY
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def ca_server(tmp_path):
    """Factory: ``start(san) -> (url, cafile, body)``.

    Mints a private CA and a leaf cert whose subjectAltName is ``DNS:{san}``,
    signed by that CA. The server is reached at ``https://localhost:{port}`` so
    the client's SNI is ``localhost`` — set ``san="localhost"`` for a match,
    anything else for a hostname mismatch against a still-trusted chain.
    """
    started = []
    ca_crt, ca_key = str(tmp_path / "ca.crt"), str(tmp_path / "ca.key")
    _openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-keyout", ca_key, "-out", ca_crt,
        "-days", "1", "-nodes", "-subj", "/CN=fizzpy Test CA",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
    )

    def start(san: str):
        tag = san.replace(".", "_")
        csr = str(tmp_path / f"{tag}.csr")
        crt = str(tmp_path / f"{tag}.crt")
        key = str(tmp_path / f"{tag}.key")
        _openssl(
            "req", "-newkey", "rsa:2048", "-keyout", key, "-out", csr,
            "-nodes", "-subj", f"/CN={san}", "-addext", f"subjectAltName=DNS:{san}",
        )
        _openssl(
            "x509", "-req", "-in", csr, "-CA", ca_crt, "-CAkey", ca_key,
            "-CAcreateserial", "-out", crt, "-days", "1",
            "-copy_extensions", "copyall",
        )
        httpd, thread, port = _serve_tls(crt, key)
        started.append((httpd, thread))
        return f"https://localhost:{port}/", ca_crt, BODY

    try:
        yield start
    finally:
        for httpd, thread in started:
            httpd.shutdown()
            thread.join(timeout=5)
