"""Shared test fixtures, including a local self-signed TLS 1.3 server.

Certificate-verification behaviour can't be tested reliably against public
endpoints: hosts with bad certs (e.g. badssl.com) are often TLS 1.2 only, and
Fizz is TLS 1.3 only, so the handshake fails for the wrong reason. A local
server with a freshly minted self-signed cert gives a deterministic, offline
target whose chain is genuinely untrusted by the system store.
"""

import http.server
import socket
import ssl
import subprocess
import threading

import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def self_signed_server(tmp_path_factory):
    """Yield the base URL of a local TLS 1.3 server using a self-signed cert."""
    d = tmp_path_factory.mktemp("tls")
    cert, key = d / "cert.pem", d / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert),
            "-days", "1", "-nodes", "-subj", "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )

    body = b"hello from local tls"

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    port = _free_port()
    httpd = http.server.HTTPServer(("127.0.0.1", port), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(str(cert), str(key))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{port}/", body
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
