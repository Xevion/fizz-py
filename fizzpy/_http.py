"""Pure-Python HTTP/1.1 request building and incremental response parsing.

This module is fully self-contained: it does no networking and has no
dependencies beyond the standard library. It turns bytes into structured
data and back, so it can sit on top of any transport (including a TLS
socket provided by the rest of fizzpy).

The centerpiece is :class:`ResponseParser`, an incremental parser that
accepts arbitrary byte chunks as they arrive off the wire. Socket reads
do not respect protocol boundaries, so every parsing step is written to
tolerate data split at any byte offset.
"""

from __future__ import annotations

import gzip
import json
import re
import zlib
from collections.abc import Iterator

__all__ = [
    "Headers",
    "HttpParseError",
    "Response",
    "ResponseParser",
    "build_request",
]


class HttpParseError(ValueError):
    """Raised when a malformed status line or header block is encountered."""


def build_request(
    method: str,
    path: str,
    host: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> bytes:
    """Build a raw HTTP/1.1 request as bytes.

    A ``Host`` header is always emitted and, when a body is present, a
    ``Content-Length`` is computed automatically. Caller-supplied headers
    win over both defaults via a case-insensitive name match, while the
    caller's original casing is preserved in the serialized output.
    """
    headers = dict(headers or {})
    supplied = {k.lower() for k in headers}

    # Defaults only fill gaps the caller did not address; we prepend them so
    # Host leads the block (conventional) while caller headers keep their order.
    defaults: list[tuple[str, str]] = []
    if "host" not in supplied:
        defaults.append(("Host", host))
    if body is not None and "content-length" not in supplied:
        defaults.append(("Content-Length", str(len(body))))

    lines = [f"{method} {path} HTTP/1.1"]
    for name, value in defaults:
        lines.append(f"{name}: {value}")
    for name, value in headers.items():
        lines.append(f"{name}: {value}")

    head = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
    return head + body if body else head


class Headers:
    """Case-insensitive, multi-value-aware mapping of response headers.

    Repeated headers are preserved as a list internally. Most lookups join
    repeats with ``", "`` per RFC 7230, but ``Set-Cookie`` is special: it
    cannot be safely comma-joined (cookies contain commas in their Expires
    attribute), so it is retrievable as a list via :meth:`get_list`.
    """

    __slots__ = ("_store",)

    def __init__(self, items: list[tuple[str, str]] | None = None) -> None:
        # Maps lowercase name -> (original-cased name, [values]).
        self._store: dict[str, tuple[str, list[str]]] = {}
        for name, value in items or []:
            self.add(name, value)

    def add(self, name: str, value: str) -> None:
        key = name.lower()
        if key in self._store:
            self._store[key][1].append(value)
        else:
            self._store[key] = (name, [value])

    def get_list(self, key: str) -> list[str]:
        """Return every value recorded for ``key`` (empty list if absent)."""
        entry = self._store.get(key.lower())
        return list(entry[1]) if entry else []

    def append_to_last(self, text: str) -> None:
        """Fold an RFC 7230 continuation line onto the most recently added value.

        Raises ``KeyError`` if no header has been added yet.
        """
        key = next(reversed(self._store))
        _, values = self._store[key]
        values[-1] = f"{values[-1]} {text}"

    def get(self, key: str, default: str | None = None) -> str | None:
        entry = self._store.get(key.lower())
        if entry is None:
            return default
        return ", ".join(entry[1])

    def __getitem__(self, key: str) -> str:
        entry = self._store.get(key.lower())
        if entry is None:
            raise KeyError(key)
        return ", ".join(entry[1])

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.lower() in self._store

    def __iter__(self) -> Iterator[str]:
        return (name for name, _ in self._store.values())

    def items(self) -> Iterator[tuple[str, str]]:
        """Yield ``(name, value)`` pairs, one per individual header line."""
        for name, values in self._store.values():
            for value in values:
                yield name, value

    def __repr__(self) -> str:
        return f"Headers({list(self.items())!r})"


_CHARSET_RE = re.compile(r"charset=([^\s;]+)", re.IGNORECASE)


class Response:
    """A fully parsed HTTP response with a decoded, de-framed body."""

    def __init__(
        self,
        status_code: int,
        reason: str,
        http_version: str,
        headers: Headers,
        content: bytes,
    ) -> None:
        self.status_code = status_code
        self.reason = reason
        self.http_version = http_version
        self.headers = headers
        self.content = content
        # Populated by the client after the transport completes.
        self.url: str = ""
        self.tls: dict[str, object] | None = None

    @property
    def text(self) -> str:
        """Decode ``content`` using the Content-Type charset (default utf-8)."""
        charset = "utf-8"
        content_type = self.headers.get("Content-Type")
        if content_type:
            match = _CHARSET_RE.search(content_type)
            if match:
                charset = match.group(1).strip().strip('"')
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            # Unknown/garbage charset label: fall back rather than raising.
            return self.content.decode("utf-8", errors="replace")

    def json(self) -> object:
        """Parse the body as JSON."""
        return json.loads(self.content)

    def __repr__(self) -> str:
        return f"<Response [{self.status_code} {self.reason}]>"


# Parser state machine phases.
_STATE_STATUS = "status"
_STATE_HEADERS = "headers"
_STATE_BODY = "body"
_STATE_DONE = "done"

_STATUS_LINE_RE = re.compile(rb"^(HTTP/\d\.\d) (\d{3})(?: (.*))?$")


class ResponseParser:
    """Incremental HTTP/1.1 response parser.

    Feed it bytes as they arrive with :meth:`feed`; call :meth:`feed_eof`
    when the connection closes. Once :meth:`is_complete` returns True the
    parsed :class:`Response` is available via :attr:`response`.

    All three RFC 7230 body-framing modes are supported: chunked transfer
    encoding, explicit Content-Length, and read-until-close. ``gzip`` and
    ``deflate`` Content-Encodings are transparently decompressed.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._state = _STATE_STATUS
        self._eof = False

        self._http_version = ""
        self._status_code = 0
        self._reason = ""
        self._headers = Headers()

        # Body framing, resolved once headers are parsed.
        self._chunked = False
        self._content_length: int | None = None
        self._read_until_close = False

        self._body = bytearray()

        # Chunked decoding cursor state, preserved across feed() calls.
        self._chunk_remaining = 0  # bytes left in the current chunk's data
        self._awaiting_chunk_size = True
        self._in_trailers = False

        self._response: Response | None = None

    @property
    def response(self) -> Response | None:
        return self._response

    def is_complete(self) -> bool:
        return self._state == _STATE_DONE

    @property
    def used_close_framing(self) -> bool:
        """True if the body was delimited by connection close (not reusable)."""
        return self._read_until_close

    def feed(self, data: bytes) -> None:
        """Append ``data`` and parse as far as the buffered bytes allow."""
        if data:
            self._buf.extend(data)
        self._parse()

    def feed_eof(self) -> None:
        """Signal that the peer closed the connection.

        For read-until-close bodies this is the only completion signal. For
        other modes an early EOF mid-body is tolerated by finalizing with
        whatever was received.
        """
        self._eof = True
        self._parse()

    def _parse(self) -> None:
        # Drive the state machine; each branch consumes from the buffer and
        # only advances when it has enough bytes, so re-entry after a partial
        # feed resumes exactly where it left off.
        if self._state == _STATE_STATUS:
            self._parse_status_line()
        if self._state == _STATE_HEADERS:
            self._parse_headers()
        if self._state == _STATE_BODY:
            self._parse_body()

    def _parse_status_line(self) -> None:
        idx = self._buf.find(b"\r\n")
        if idx == -1:
            if self._eof and self._buf:
                raise HttpParseError("connection closed before status line")
            return
        line = bytes(self._buf[:idx])
        del self._buf[: idx + 2]

        match = _STATUS_LINE_RE.match(line)
        if not match:
            raise HttpParseError(f"malformed status line: {line!r}")
        self._http_version = match.group(1).decode("latin-1")
        self._status_code = int(match.group(2))
        self._reason = (match.group(3) or b"").decode("latin-1")
        self._state = _STATE_HEADERS

    def _parse_headers(self) -> None:
        # A leading CRLF means the header block is empty (status line then the
        # terminating blank line, e.g. "HTTP/1.1 204 No Content\r\n\r\n").
        if self._buf.startswith(b"\r\n"):
            del self._buf[:2]
            block = b""
        else:
            # Otherwise headers end at the first blank line. Wait until the full
            # terminator is buffered so a split across feeds never truncates it.
            end = self._buf.find(b"\r\n\r\n")
            if end == -1:
                if self._eof and self._buf:
                    raise HttpParseError("connection closed inside headers")
                return
            block = bytes(self._buf[:end])
            del self._buf[: end + 4]

        for raw in block.split(b"\r\n"):
            if not raw:
                continue
            # Folded (continuation) lines begin with whitespace and append to
            # the previous value; rare but legal in RFC 7230.
            if raw[:1] in (b" ", b"\t"):
                if not list(self._headers.items()):
                    raise HttpParseError("header continuation with no prior header")
                self._headers.append_to_last(raw.strip().decode("latin-1"))
                continue
            colon = raw.find(b":")
            if colon <= 0:
                raise HttpParseError(f"malformed header line: {raw!r}")
            name = raw[:colon].decode("latin-1").strip()
            value = raw[colon + 1 :].decode("latin-1").strip()
            self._headers.add(name, value)

        self._resolve_framing()
        self._state = _STATE_BODY
        self._parse_body()

    def _resolve_framing(self) -> None:
        te = self._headers.get("Transfer-Encoding")
        if te and "chunked" in te.lower():
            self._chunked = True
            return

        # 1xx/204/304 are defined to carry no body regardless of headers.
        if self._status_code < 200 or self._status_code in (204, 304):
            self._content_length = 0
            return

        cl = self._headers.get("Content-Length")
        if cl is not None:
            try:
                self._content_length = int(cl.strip())
            except ValueError as exc:
                raise HttpParseError(f"invalid Content-Length: {cl!r}") from exc
            return

        # No framing headers: the body is delimited by connection close.
        self._read_until_close = True

    def _parse_body(self) -> None:
        if self._chunked:
            self._parse_chunked()
        elif self._content_length is not None:
            self._parse_fixed_length()
        else:
            self._parse_until_close()

    def _parse_fixed_length(self) -> None:
        assert self._content_length is not None
        need = self._content_length - len(self._body)
        if need > 0:
            take = min(need, len(self._buf))
            self._body.extend(self._buf[:take])
            del self._buf[:take]
        if len(self._body) >= self._content_length:
            self._finalize()
        elif self._eof:
            # Short read: peer hung up early. Finalize with what we have rather
            # than blocking forever.
            self._finalize()

    def _parse_until_close(self) -> None:
        if self._buf:
            self._body.extend(self._buf)
            self._buf.clear()
        if self._eof:
            self._finalize()

    def _parse_chunked(self) -> None:
        # Decode chunks incrementally. We never assume a full chunk is present;
        # each loop iteration either makes progress or returns to await bytes.
        while True:
            if self._in_trailers:
                end = self._buf.find(b"\r\n\r\n")
                # Trailers may be absent, in which case the terminator already
                # appeared as a lone CRLF consumed below; handle both shapes.
                if self._buf.startswith(b"\r\n"):
                    del self._buf[:2]
                    self._finalize()
                    return
                if end == -1:
                    if self._eof:
                        self._finalize()
                    return
                del self._buf[: end + 4]
                self._finalize()
                return

            if self._awaiting_chunk_size:
                idx = self._buf.find(b"\r\n")
                if idx == -1:
                    if self._eof and self._buf:
                        raise HttpParseError("EOF inside chunk size line")
                    return
                size_line = bytes(self._buf[:idx])
                # Chunk extensions follow a ';' and are ignored.
                size_token = size_line.split(b";", 1)[0].strip()
                try:
                    chunk_size = int(size_token, 16)
                except ValueError as exc:
                    raise HttpParseError(f"invalid chunk size: {size_line!r}") from exc
                del self._buf[: idx + 2]
                if chunk_size == 0:
                    # Final chunk: what follows is optional trailers then CRLF.
                    self._in_trailers = True
                    continue
                self._chunk_remaining = chunk_size
                self._awaiting_chunk_size = False

            # Consume this chunk's data plus its trailing CRLF.
            if self._chunk_remaining > 0:
                take = min(self._chunk_remaining, len(self._buf))
                self._body.extend(self._buf[:take])
                del self._buf[:take]
                self._chunk_remaining -= take
                if self._chunk_remaining > 0:
                    if self._eof:
                        raise HttpParseError("EOF inside chunk data")
                    return

            # Chunk data complete; expect the CRLF separator before the next size.
            if len(self._buf) < 2:
                if self._eof:
                    raise HttpParseError("EOF before chunk terminator")
                return
            if not self._buf.startswith(b"\r\n"):
                raise HttpParseError("missing CRLF after chunk data")
            del self._buf[:2]
            self._awaiting_chunk_size = True

    def _finalize(self) -> None:
        content = self._decompress(bytes(self._body))
        self._response = Response(
            status_code=self._status_code,
            reason=self._reason,
            http_version=self._http_version,
            headers=self._headers,
            content=content,
        )
        self._state = _STATE_DONE

    def _decompress(self, data: bytes) -> bytes:
        encoding = self._headers.get("Content-Encoding")
        if not encoding or not data:
            return data
        encoding = encoding.lower().strip()
        try:
            if encoding == "gzip":
                return gzip.decompress(data)
            if encoding == "deflate":
                # "deflate" per the HTTP spec means zlib-wrapped, but many
                # servers send raw DEFLATE. Try zlib first, then raw.
                try:
                    return zlib.decompress(data)
                except zlib.error:
                    return zlib.decompress(data, -zlib.MAX_WBITS)
        except (OSError, zlib.error):
            # Decompression failed: surface the raw bytes rather than crashing.
            return data
        return data
