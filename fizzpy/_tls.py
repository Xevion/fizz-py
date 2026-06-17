"""The pluggable TLS layer: wrap an already-connected socket in a Fizz handshake.

This is what lets fizzpy sit *under* an existing HTTP client (requests, httpx,
aiohttp) instead of replacing it. The client opens its own TCP connection — with
its own DNS, proxy, and pooling — and hands the socket here; fizzpy performs the
TLS 1.3 (optionally post-quantum) handshake over that socket and returns a
blocking, socket-like object the client can read and write as if it were an
``ssl.SSLSocket``.

    import socket, fizzpy

    tcp = socket.create_connection(("www.cloudflare.com", 443))
    tls = fizzpy.wrap_socket(tcp, "www.cloudflare.com")
    tls.sendall(b"GET / HTTP/1.1\r\nHost: www.cloudflare.com\r\n"
                b"Connection: close\r\n\r\n")
    print(tls.tls["group"])            # X25519MLKEM768
    print(tls.recv(64))

:class:`TlsConfig` carries the handshake knobs (groups, ALPN, verification,
custom ClientHello extensions); the per-library adapters in :mod:`fizzpy.contrib`
build on this primitive.
"""

from __future__ import annotations

import io
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from . import _core  # pyright: ignore[reportPrivateUsage]  # our own extension module
from ._common import (
    DEFAULT_ALPN,
    DEFAULT_GROUPS,
    DEFAULT_TIMEOUT_MS,
    READ_DONE,
    default_ca_file,
    normalize_extensions,
)
from ._transport import run_sync

__all__ = ["TlsConfig", "TlsSocket", "wrap_socket"]


@dataclass(frozen=True)
class TlsConfig:
    """Handshake parameters for :func:`wrap_socket` and the contrib adapters.

    Mirrors the knobs the Fizz core exposes per connection. Defaults match
    fizzpy's standalone client: certifi-backed verification with hostname
    checking, HTTP/1.1 ALPN, and a post-quantum-first key share
    (``X25519MLKEM768`` then ``x25519``).
    """

    verify: bool = True
    cafile: str | None = None
    alpn: Sequence[str] = field(default_factory=lambda: list(DEFAULT_ALPN))
    groups: Sequence[_core.NamedGroup] = field(
        default_factory=lambda: list(DEFAULT_GROUPS)
    )
    extensions: Sequence[tuple[int, bytes]] = ()
    timeout: float = DEFAULT_TIMEOUT_MS / 1000

    @property
    def resolved_cafile(self) -> str:
        """The CA bundle to trust — the caller's, or certifi's by default."""
        return self.cafile or default_ca_file()

    @property
    def timeout_ms(self) -> int:
        return int(self.timeout * 1000)

    def normalized_extensions(self) -> list[tuple[int, bytes]]:
        return normalize_extensions(self.extensions)


class _TlsRawIO(io.RawIOBase):
    """Raw byte stream over a :class:`TlsSocket`, for ``makefile``.

    ``http.client`` reads responses through ``sock.makefile("rb")``; this adapts
    the socket's ``recv``/``send`` to the ``RawIOBase`` interface a
    ``BufferedReader``/``BufferedWriter`` sits on. Closing the file does not
    close the underlying TLS socket (the owner manages its lifetime), mirroring
    how ``socket.SocketIO`` defers to the socket.
    """

    def __init__(self, sock: TlsSocket, mode: str) -> None:
        super().__init__()
        self._sock = sock
        self._mode = mode

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        data = self._sock.recv(len(b))
        n = len(data)
        b[:n] = data
        return n

    def write(self, b: Any) -> int:
        return self._sock.send(b)

    def readable(self) -> bool:
        return "r" in self._mode

    def writable(self) -> bool:
        return "w" in self._mode

    def seekable(self) -> bool:
        return False


class TlsSocket:
    """A blocking, ``ssl.SSLSocket``-shaped view of a Fizz TLS connection.

    Presents the slice of the socket API that ``http.client``/urllib3 use to
    drive a request over a TLS connection: ``recv``/``recv_into``, ``send``/
    ``sendall``, ``makefile``, ``settimeout``, and ``close``. Decrypted bytes are
    pulled from the C++ core one chunk at a time and re-sliced to honour
    ``recv``'s size bound.

    The negotiated TLS 1.3 parameters are available as :attr:`tls`.
    """

    def __init__(
        self,
        conn: _core.TlsConnection,
        server_hostname: str,
        timeout: float | None,
        fd: int = -1,
    ) -> None:
        self._conn = conn
        self._server_hostname = server_hostname
        self._timeout = timeout
        # The duplicated TCP fd Fizz owns. Exposed read-only via fileno() so
        # callers can poll readiness (urllib3's keep-alive reuse check); never
        # closed from Python — the C++ core closes it on teardown.
        self._fd = fd
        self._rbuf = b""
        self._eof = False
        self._closed = False

    @property
    def tls(self) -> dict[str, object]:
        """Negotiated TLS 1.3 parameters (version, cipher, group, ALPN, ...)."""
        return self._conn.negotiated()

    @property
    def server_hostname(self) -> str:
        return self._server_hostname

    def recv(self, bufsize: int = 65536, flags: int = 0) -> bytes:
        if self._rbuf:
            out, self._rbuf = self._rbuf[:bufsize], self._rbuf[bufsize:]
            return out
        if self._eof:
            return b""
        chunk = run_sync(lambda resolve, reject: self._conn.read(resolve, reject))
        if chunk == READ_DONE:
            self._eof = True
            return b""
        out, self._rbuf = chunk[:bufsize], chunk[bufsize:]
        return out

    def recv_into(self, buffer: bytearray | memoryview, nbytes: int = 0) -> int:
        size = nbytes or len(buffer)
        data = self.recv(size)
        n = len(data)
        buffer[:n] = data
        return n

    def sendall(self, data: Any, flags: int = 0) -> None:
        run_sync(lambda resolve, reject: self._conn.write(bytes(data), resolve, reject))

    def send(self, data: Any, flags: int = 0) -> int:
        payload = bytes(data)
        self.sendall(payload)
        return len(payload)

    def makefile(
        self,
        mode: str = "r",
        buffering: int | None = None,
        *,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> Any:
        """A file object over the connection, mirroring ``socket.makefile``.

        Supports the binary/text read/write modes ``http.client`` needs; closing
        the returned file does not close this socket.
        """
        writing = "w" in mode
        reading = "r" in mode or not writing
        binary = "b" in mode
        rawmode = ("r" if reading else "") + ("w" if writing else "")
        raw = _TlsRawIO(self, rawmode)
        if buffering is None:
            buffering = io.DEFAULT_BUFFER_SIZE
        if buffering == 0:
            if not binary:
                raise ValueError("unbuffered streams must be binary")
            return raw
        if reading and writing:
            buffer: io.BufferedIOBase = io.BufferedRWPair(raw, raw, buffering)
        elif reading:
            buffer = io.BufferedReader(raw, buffering)
        else:
            buffer = io.BufferedWriter(raw, buffering)
        if binary:
            return buffer
        # TextIOWrapper accepts these buffers at runtime; typeshed's _WrappedBuffer
        # protocol wants a `name` attribute BufferedRWPair lacks (as does socket's).
        return io.TextIOWrapper(buffer, encoding, errors, newline)  # pyright: ignore[reportArgumentType]

    def settimeout(self, timeout: float | None) -> None:
        # Stored for API compatibility; the handshake already honours the
        # configured timeout. Per-read deadlines are not yet enforced.
        self._timeout = timeout

    def gettimeout(self) -> float | None:
        return self._timeout

    def setsockopt(self, *args: object) -> None:
        # Socket options belong on the raw TCP socket (set before the handshake);
        # accepted as a no-op so callers that poke the wrapped socket don't break.
        return None

    def fileno(self) -> int:
        # The fd Fizz reads from. Returned so callers can poll read-readiness
        # (urllib3's idle keep-alive reuse check). Fizz's loop also reads this fd,
        # so a poll is a non-consuming readiness probe — fine for well-behaved
        # HTTP keep-alive, where an idle connection carries no unsolicited data.
        if self._closed or self._fd < 0:
            raise OSError("operation on a closed fizzpy TlsSocket")
        return self._fd

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._fd = -1  # the C++ core owns and closes the underlying fd
            self._conn.close()

    def __enter__(self) -> TlsSocket:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def wrap_socket(
    sock: Any,
    server_hostname: str,
    config: TlsConfig | None = None,
) -> TlsSocket:
    """Perform a Fizz TLS handshake over an already-connected socket.

    ``sock`` must be a connected TCP socket (anything with a ``fileno()``). Its
    file descriptor is duplicated and the copy is handed to the Fizz event loop,
    which owns and eventually closes it — so the caller keeps full control of
    ``sock`` itself (close it whenever; the TLS connection lives on independently
    through the dup). ``server_hostname`` is the SNI and the name the certificate
    is matched against.

    Returns a :class:`TlsSocket`. Raises on handshake or verification failure.
    """
    config = config or TlsConfig()
    conn = _core.TlsConnection()
    dup = os.dup(sock.fileno())
    # wrap_fd takes ownership of `dup` on every outcome (it closes it on failure
    # too), so there is no fd to clean up here regardless of success.
    run_sync(
        lambda resolve, reject: conn.wrap_fd(
            dup,
            server_hostname,
            list(config.alpn),
            list(config.groups),
            config.verify,
            config.resolved_cafile,
            config.timeout_ms,
            config.normalized_extensions(),
            resolve,
            reject,
        )
    )
    return TlsSocket(conn, server_hostname, config.timeout, dup)
