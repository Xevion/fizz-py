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


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly ``n`` bytes, or fewer if the peer closes first."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


@pytest.fixture
def raw_clienthello_server():
    """A plain-socket listener that captures the first TLS record, then closes.

    No TLS is spoken: the worker reads one ``handshake(22)`` record (the
    ClientHello) off the wire, stashes its body, and drops the connection so the
    client's handshake fails. Lets a test inspect exactly what fizzpy sent
    without completing a handshake. Exposes ``.url`` and ``.clienthello``.
    """
    port = _free_port()
    srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("::", port))
    srv.listen(1)
    captured = {}

    def serve():
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        with conn:
            header = _recv_exact(conn, 5)
            if len(header) == 5 and header[0] == 0x16:  # handshake record
                length = int.from_bytes(header[3:5], "big")
                captured["record"] = _recv_exact(conn, length)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    class Handle:
        url = f"https://127.0.0.1:{port}/"

        @property
        def clienthello(self):
            return captured.get("record")

    try:
        yield Handle()
    finally:
        srv.close()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def self_signed_server(tmp_path_factory):
    """Yield ``(url, body)`` for a server using an untrusted self-signed cert."""
    d = tmp_path_factory.mktemp("selfsigned")
    cert, key = str(d / "cert.pem"), str(d / "key.pem")
    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-keyout",
        key,
        "-out",
        cert,
        "-days",
        "1",
        "-nodes",
        "-subj",
        "/CN=localhost",
    )
    httpd, thread, port = _serve_tls(cert, key)
    try:
        yield f"https://127.0.0.1:{port}/", BODY
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


class _CountingServer(_DualStackServer):
    """Dual-stack server that counts accepted TCP connections.

    With HTTP/1.1 keep-alive, one connection serves many requests, so the
    connection count (not the request count) is what reveals reuse.
    """

    connections = 0

    def get_request(self):
        type(self).connections += 1
        return super().get_request()


def _serve_app(cert: str, key: str):
    """A persistent (HTTP/1.1) TLS server with redirect + method-echo routes."""

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _body(self, status: int, payload: bytes, extra=()):
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            for name, value in extra:
                self.send_header(name, value)
            self.end_headers()
            if payload:
                self.wfile.write(payload)

        def _consume_request_body(self):
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)

        def _redirect(self, location: str, status: int = 302):
            self._body(status, b"", extra=[("Location", location)])

        def _route(self):
            self._consume_request_body()
            path = self.path
            if path == "/":
                self._body(200, BODY)
            elif path == "/echo-method":
                self._body(200, self.command.encode())
            elif path == "/redirect":
                self._redirect("/")
            elif path == "/redirect-303":
                self._redirect("/echo-method", status=303)
            elif path == "/redirect-307":
                self._redirect("/echo-method", status=307)
            elif path == "/loop":
                self._redirect("/loop")
            elif path.startswith("/chain/"):
                n = int(path.rsplit("/", 1)[1])
                self._redirect("/" if n <= 1 else f"/chain/{n - 1}")
            else:
                self._body(404, b"not found")

        do_GET = _route
        do_POST = _route

        def log_message(self, *args):
            pass

    port = _free_port()
    _CountingServer.connections = 0
    httpd = _CountingServer(("::", port), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(cert, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, port


@pytest.fixture
def local_server(tmp_path):
    """Yield a persistent self-signed TLS server (use ``verify=False``).

    Exposes ``.url`` plus a ``.connections`` count of accepted TCP connections,
    and routes for redirect / method-echo / keep-alive testing.
    """
    cert, key = str(tmp_path / "c.pem"), str(tmp_path / "k.pem")
    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-keyout",
        key,
        "-out",
        cert,
        "-days",
        "1",
        "-nodes",
        "-subj",
        "/CN=localhost",
    )
    httpd, thread, port = _serve_app(cert, key)

    class Handle:
        url = f"https://127.0.0.1:{port}/"

        @property
        def connections(self) -> int:
            return _CountingServer.connections

    try:
        yield Handle()
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
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-keyout",
        ca_key,
        "-out",
        ca_crt,
        "-days",
        "1",
        "-nodes",
        "-subj",
        "/CN=fizzpy Test CA",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
    )

    def start(san: str):
        tag = san.replace(".", "_")
        csr = str(tmp_path / f"{tag}.csr")
        crt = str(tmp_path / f"{tag}.crt")
        key = str(tmp_path / f"{tag}.key")
        _openssl(
            "req",
            "-newkey",
            "rsa:2048",
            "-keyout",
            key,
            "-out",
            csr,
            "-nodes",
            "-subj",
            f"/CN={san}",
            "-addext",
            f"subjectAltName=DNS:{san}",
        )
        _openssl(
            "x509",
            "-req",
            "-in",
            csr,
            "-CA",
            ca_crt,
            "-CAkey",
            ca_key,
            "-CAcreateserial",
            "-out",
            crt,
            "-days",
            "1",
            "-copy_extensions",
            "copyall",
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
