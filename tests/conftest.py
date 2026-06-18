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

import contextlib
import http.server
import socket
import ssl
import subprocess
import threading

import pytest

BODY = b"hello from local tls"


class _DualStackServer(http.server.ThreadingHTTPServer):
    # "localhost" may resolve to ::1 or 127.0.0.1 depending on the resolver;
    # bind a dual-stack IPv6 socket so the client reaches us either way.
    # Threaded so concurrent keep-alive connections are each served on their own
    # thread — a single-threaded server would let one persistent connection
    # starve all the others (see test_concurrency).
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def _serve_tls(cert: str, key: str, *, max_version: "ssl.TLSVersion | None" = None):
    """Start a dual-stack TLS HTTP server; return (httpd, thread, port).

    Defaults to TLS 1.3 only (the version Fizz speaks). Pass ``max_version`` to
    cap the server below 1.3 — e.g. ``ssl.TLSVersion.TLSv1_2`` for a server Fizz
    cannot handshake, used to exercise the opt-in stdlib fallback.
    """

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(BODY)))
            self.end_headers()
            self.wfile.write(BODY)

        def log_message(self, *args):
            pass

    # Bind port 0 and read back the assigned port: no close-then-rebind gap for
    # another listener to slip into, so concurrent fixtures can't race for a port.
    httpd = _DualStackServer(("::", 0), Handler)
    port = httpd.server_address[1]
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if max_version is None:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    else:
        # Pin both ends so the server's version envelope is deterministic and
        # doesn't drift with the stdlib/OpenSSL default minimum.
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = max_version
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
    srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("::", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
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


@pytest.fixture
def tls12_server(tmp_path):
    """Yield a self-signed server capped at TLS 1.2, which Fizz cannot handshake.

    Fizz fails against it with a ``protocol_version`` alert; the opt-in stdlib
    fallback (``fallback=True``) completes the handshake classically instead.
    Exposes ``.url`` (use ``verify=False`` — the cert is self-signed).
    """
    cert, key = str(tmp_path / "c.pem"), str(tmp_path / "k.pem")
    _openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-keyout", key, "-out", cert,
        "-days", "1", "-nodes", "-subj", "/CN=localhost",
    )  # fmt: skip
    httpd, thread, port = _serve_tls(cert, key, max_version=ssl.TLSVersion.TLSv1_2)

    class Handle:
        url = f"https://127.0.0.1:{port}/"

    try:
        yield Handle()
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def stalling_server(tmp_path):
    """A TLS 1.3 server that completes the handshake then never responds.

    The Fizz handshake succeeds, but the application read blocks forever — used
    to verify read deadlines are enforced (a stalled peer must raise
    socket.timeout, not hang the caller). Exposes ``.url`` (use ``verify=False``).
    """
    cert, key = str(tmp_path / "c.pem"), str(tmp_path / "k.pem")
    _openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-keyout", key, "-out", cert,
        "-days", "1", "-nodes", "-subj", "/CN=localhost",
    )  # fmt: skip
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(cert, key)

    srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("::", 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    srv.settimeout(0.25)
    stop = threading.Event()
    held: list[ssl.SSLSocket] = []

    def serve():
        while not stop.is_set():
            try:
                raw, _ = srv.accept()
            except OSError:
                continue
            try:
                # Bound the server-side handshake so a client that gives up
                # mid-handshake can't wedge this single serve thread. Complete
                # the handshake, then hold the connection open without ever
                # writing a response, so the client's read stalls.
                raw.settimeout(5)
                held.append(ctx.wrap_socket(raw, server_side=True))
            except OSError:
                raw.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    class Handle:
        url = f"https://127.0.0.1:{port}/"

    try:
        yield Handle()
    finally:
        stop.set()
        srv.close()
        thread.join(timeout=5)
        for conn in held:
            conn.close()


@pytest.fixture
def connect_proxy():
    """A minimal HTTP ``CONNECT`` proxy that tunnels to any host:port.

    Lets a test confirm fizzpy reaches an HTTPS host *through* a proxy: the HTTP
    client performs the CONNECT and hands fizzpy an already-tunnelled socket, so
    the Fizz handshake rides over the tunnel unchanged — fizzpy never sees the
    proxy. Exposes ``.url`` and a ``.connects`` count of tunnels opened.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    srv.settimeout(0.25)
    stop = threading.Event()
    counter = {"n": 0}

    def pipe(src: socket.socket, dst: socket.socket):
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            for s in (src, dst):
                with contextlib.suppress(OSError):
                    s.shutdown(socket.SHUT_RDWR)

    def handle(client: socket.socket):
        upstream = None
        try:
            req = b""
            while b"\r\n\r\n" not in req:
                chunk = client.recv(4096)
                if not chunk:
                    return
                req += chunk
            method, target, _ = req.split(b"\r\n", 1)[0].decode("latin1").split(" ", 2)
            if method != "CONNECT":
                client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                return
            host, _, p = target.partition(":")
            upstream = socket.create_connection((host, int(p)))
            counter["n"] += 1
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            threading.Thread(target=pipe, args=(upstream, client), daemon=True).start()
            pipe(client, upstream)
        except OSError:
            pass
        finally:
            client.close()
            if upstream is not None:
                upstream.close()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    class Handle:
        url = f"http://127.0.0.1:{port}"

        @property
        def connects(self) -> int:
            return counter["n"]

    try:
        yield Handle()
    finally:
        stop.set()
        srv.close()
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

    _CountingServer.connections = 0
    httpd = _CountingServer(("::", 0), Handler)
    port = httpd.server_address[1]
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
    ca_csr = str(tmp_path / "ca.csr")
    ca_ext = tmp_path / "ca.ext"
    # Self-sign the CA via `x509 -req -extfile` rather than `req -x509 -addext`.
    # On OpenSSL 1.1 (the manylinux build env) `req -x509` already injects the
    # config's default v3_ca extensions, so -addext *duplicates* basicConstraints
    # — a malformed cert that 1.1 then rejects as an issuer. `x509 -req` adds only
    # the extfile's extensions, so the chain is valid on both 1.1 and 3.0.
    ca_ext.write_text(
        "basicConstraints=critical,CA:TRUE\n"
        "keyUsage=critical,keyCertSign,cRLSign\n"
        "subjectKeyIdentifier=hash\n"
    )
    _openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-keyout",
        ca_key,
        "-out",
        ca_csr,
        "-nodes",
        "-subj",
        "/CN=fizzpy Test CA",
    )
    _openssl(
        "x509",
        "-req",
        "-in",
        ca_csr,
        "-signkey",
        ca_key,
        "-days",
        "1",
        "-extfile",
        str(ca_ext),
        "-out",
        ca_crt,
    )

    def start(san: str):
        tag = san.replace(".", "_")
        csr = str(tmp_path / f"{tag}.csr")
        crt = str(tmp_path / f"{tag}.crt")
        key = str(tmp_path / f"{tag}.key")
        ext = tmp_path / f"{tag}.ext"
        # Supply the SAN to the signing step via -extfile rather than copying it
        # from the CSR with `-copy_extensions copyall` (an OpenSSL 3.0-only flag;
        # the manylinux build env ships OpenSSL 1.1). -extfile works on both.
        ext.write_text(f"basicConstraints=CA:FALSE\nsubjectAltName=DNS:{san}\n")
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
            "-extfile",
            str(ext),
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
