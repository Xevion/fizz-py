"""Tests for the pure-Python HTTP/1.1 framing module (fizzpy._http)."""

from __future__ import annotations

import gzip
import json
import zlib

import pytest

from fizzpy._http import (
    Headers,
    HttpParseError,
    Response,
    ResponseParser,
    build_request,
)


def parse_all(*chunks: bytes, eof: bool = False) -> Response:
    """Feed chunks to a parser and return the finished response."""
    parser = ResponseParser()
    for chunk in chunks:
        parser.feed(chunk)
    if eof:
        parser.feed_eof()
    assert parser.is_complete(), "parser did not complete"
    assert parser.response is not None
    return parser.response


class TestBuildRequest:
    def test_basic_request_line_and_host(self):
        raw = build_request("GET", "/index.html", "example.com")
        assert raw.startswith(b"GET /index.html HTTP/1.1\r\n")
        assert b"Host: example.com\r\n" in raw
        assert raw.endswith(b"\r\n\r\n")

    def test_returns_bytes(self):
        assert isinstance(build_request("GET", "/", "h"), bytes)

    def test_content_length_auto_added_with_body(self):
        body = b'{"a":1}'
        raw = build_request("POST", "/api", "example.com", body=body)
        assert f"Content-Length: {len(body)}".encode() in raw
        assert raw.endswith(b"\r\n\r\n" + body)

    def test_no_content_length_without_body(self):
        raw = build_request("GET", "/", "example.com")
        assert b"Content-Length" not in raw

    def test_caller_host_overrides_default_case_insensitive(self):
        raw = build_request("GET", "/", "default.com", headers={"host": "custom.com"})
        assert b"custom.com" in raw
        assert b"default.com" not in raw
        # Caller casing preserved (lowercase "host").
        assert b"host: custom.com" in raw

    def test_caller_content_length_overrides_auto(self):
        body = b"hello"
        raw = build_request(
            "POST", "/", "h", headers={"Content-Length": "99"}, body=body
        )
        assert b"Content-Length: 99" in raw
        assert b"Content-Length: 5" not in raw

    def test_caller_header_casing_preserved(self):
        raw = build_request("GET", "/", "h", headers={"X-Custom-Thing": "v"})
        assert b"X-Custom-Thing: v" in raw

    def test_body_bytes_appended(self):
        raw = build_request("PUT", "/x", "h", body=b"\x00\x01\x02")
        assert raw.endswith(b"\x00\x01\x02")


class TestHeaders:
    def test_case_insensitive_get(self):
        h = Headers([("Content-Type", "text/html")])
        assert h["content-type"] == "text/html"
        assert h.get("CONTENT-TYPE") == "text/html"

    def test_get_default(self):
        h = Headers()
        assert h.get("missing") is None
        assert h.get("missing", "x") == "x"

    def test_missing_key_raises(self):
        with pytest.raises(KeyError):
            _ = Headers()["nope"]

    def test_multi_value_joined(self):
        h = Headers([("Accept", "text/html"), ("Accept", "application/json")])
        assert h["accept"] == "text/html, application/json"

    def test_set_cookie_as_list(self):
        h = Headers([("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])
        assert h.get_list("set-cookie") == ["a=1", "b=2"]

    def test_get_list_general(self):
        h = Headers([("X-Tag", "1"), ("X-Tag", "2")])
        assert h.get_list("x-tag") == ["1", "2"]
        assert h.get_list("absent") == []

    def test_contains(self):
        h = Headers([("Foo", "bar")])
        assert "foo" in h
        assert "FOO" in h
        assert "baz" not in h

    def test_items_and_iter(self):
        h = Headers([("A", "1"), ("A", "2"), ("B", "3")])
        assert list(h.items()) == [("A", "1"), ("A", "2"), ("B", "3")]
        assert list(h) == ["A", "B"]

    def test_repr(self):
        assert "Headers(" in repr(Headers([("A", "1")]))


class TestContentLengthFraming:
    def test_simple(self):
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"hello"
        )
        resp = parse_all(raw)
        assert resp.status_code == 200
        assert resp.reason == "OK"
        assert resp.http_version == "HTTP/1.1"
        assert resp.content == b"hello"

    def test_body_split_across_feeds(self):
        parser = ResponseParser()
        parser.feed(b"HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\nhel")
        assert not parser.is_complete()
        parser.feed(b"lo ")
        assert not parser.is_complete()
        parser.feed(b"world")
        assert parser.is_complete()
        assert parser.response.content == b"hello world"

    def test_headers_split_across_feeds(self):
        parser = ResponseParser()
        parser.feed(b"HTTP/1.1 200 ")
        parser.feed(b"OK\r\nContent-Len")
        parser.feed(b"gth: 3\r\n\r\nabc")
        assert parser.is_complete()
        assert parser.response.content == b"abc"


class TestChunkedFraming:
    def test_simple_chunked(self):
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"5\r\nhello\r\n"
            b"6\r\n world\r\n"
            b"0\r\n\r\n"
        )
        resp = parse_all(raw)
        assert resp.content == b"hello world"

    def test_chunk_extensions_ignored(self):
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"5;name=value\r\nhello\r\n"
            b"0\r\n\r\n"
        )
        assert parse_all(raw).content == b"hello"

    def test_chunked_with_trailers(self):
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"4\r\nWiki\r\n"
            b"0\r\n"
            b"X-Trailer: value\r\n"
            b"\r\n"
        )
        assert parse_all(raw).content == b"Wiki"

    def test_chunked_byte_by_byte(self):
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"5\r\nhello\r\n"
            b"6\r\n world\r\n"
            b"0\r\n\r\n"
        )
        parser = ResponseParser()
        for i, byte in enumerate(raw):
            parser.feed(bytes([byte]))
            # Must not complete before the final terminator arrives.
            if i < len(raw) - 1:
                assert not parser.is_complete()
        assert parser.is_complete()
        assert parser.response.content == b"hello world"


class TestConnectionCloseFraming:
    def test_body_until_eof(self):
        parser = ResponseParser()
        parser.feed(b"HTTP/1.1 200 OK\r\n\r\n")
        parser.feed(b"some body ")
        parser.feed(b"data")
        assert not parser.is_complete()
        parser.feed_eof()
        assert parser.is_complete()
        assert parser.response.content == b"some body data"

    def test_eof_with_no_body(self):
        parser = ResponseParser()
        parser.feed(b"HTTP/1.1 200 OK\r\n\r\n")
        parser.feed_eof()
        assert parser.is_complete()
        assert parser.response.content == b""


class TestNoBodyStatuses:
    def test_204_completes_immediately(self):
        resp = parse_all(b"HTTP/1.1 204 No Content\r\n\r\n")
        assert resp.status_code == 204
        assert resp.content == b""

    def test_304_completes_immediately(self):
        resp = parse_all(b"HTTP/1.1 304 Not Modified\r\nETag: \"abc\"\r\n\r\n")
        assert resp.status_code == 304
        assert resp.content == b""

    def test_204_ignores_content_length(self):
        # Even with a bogus Content-Length, 204 carries no body.
        resp = parse_all(b"HTTP/1.1 204 No Content\r\nContent-Length: 10\r\n\r\n")
        assert resp.content == b""


class TestDecompression:
    def test_gzip_roundtrip(self):
        payload = b"the quick brown fox" * 10
        compressed = gzip.compress(payload)
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Encoding: gzip\r\n"
            + f"Content-Length: {len(compressed)}\r\n".encode()
            + b"\r\n"
            + compressed
        )
        assert parse_all(raw).content == payload

    def test_deflate_zlib_wrapped(self):
        payload = b"deflate me please" * 5
        compressed = zlib.compress(payload)
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Encoding: deflate\r\n"
            + f"Content-Length: {len(compressed)}\r\n".encode()
            + b"\r\n"
            + compressed
        )
        assert parse_all(raw).content == payload

    def test_deflate_raw(self):
        payload = b"raw deflate stream" * 4
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        compressed = compressor.compress(payload) + compressor.flush()
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Encoding: deflate\r\n"
            + f"Content-Length: {len(compressed)}\r\n".encode()
            + b"\r\n"
            + compressed
        )
        assert parse_all(raw).content == payload

    def test_corrupt_compression_left_as_is(self):
        garbage = b"not actually gzip"
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Encoding: gzip\r\n"
            + f"Content-Length: {len(garbage)}\r\n".encode()
            + b"\r\n"
            + garbage
        )
        assert parse_all(raw).content == garbage

    def test_chunked_then_gzip(self):
        payload = b"chunked and gzipped" * 8
        compressed = gzip.compress(payload)
        body = b"%x\r\n" % len(compressed) + compressed + b"\r\n0\r\n\r\n"
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"Content-Encoding: gzip\r\n"
            b"\r\n" + body
        )
        assert parse_all(raw).content == payload


class TestResponseHelpers:
    def test_text_default_utf8(self):
        resp = Response(200, "OK", "HTTP/1.1", Headers(), "héllo".encode("utf-8"))
        assert resp.text == "héllo"

    def test_text_charset_from_content_type(self):
        h = Headers([("Content-Type", "text/html; charset=latin-1")])
        resp = Response(200, "OK", "HTTP/1.1", h, "café".encode("latin-1"))
        assert resp.text == "café"

    def test_text_replaces_undecodable(self):
        resp = Response(200, "OK", "HTTP/1.1", Headers(), b"\xff\xfe")
        # errors="replace" must not raise.
        assert isinstance(resp.text, str)

    def test_json(self):
        resp = Response(200, "OK", "HTTP/1.1", Headers(), b'{"key": [1, 2, 3]}')
        assert resp.json() == {"key": [1, 2, 3]}

    def test_repr(self):
        resp = Response(200, "OK", "HTTP/1.1", Headers(), b"")
        assert repr(resp) == "<Response [200 OK]>"


class TestMalformedInput:
    def test_bad_status_line(self):
        parser = ResponseParser()
        with pytest.raises(HttpParseError):
            parser.feed(b"GARBAGE LINE HERE\r\n")

    def test_bad_header_line(self):
        parser = ResponseParser()
        with pytest.raises(HttpParseError):
            parser.feed(b"HTTP/1.1 200 OK\r\nnocolon\r\n\r\n")

    def test_bad_chunk_size(self):
        parser = ResponseParser()
        with pytest.raises(HttpParseError):
            parser.feed(
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nZZZ\r\n"
            )

    def test_http_parse_error_is_value_error(self):
        assert issubclass(HttpParseError, ValueError)


class TestFullIncrementalResponse:
    def test_realistic_response_one_byte_at_a_time(self):
        payload = json.dumps({"message": "hello world", "items": [1, 2, 3]}).encode()
        raw = (
            b"HTTP/1.1 200 OK\r\n"
            b"Server: fizz/1.0\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            b"Set-Cookie: session=abc\r\n"
            b"Set-Cookie: tracking=xyz\r\n"
            + f"Content-Length: {len(payload)}\r\n".encode()
            + b"\r\n"
            + payload
        )
        parser = ResponseParser()
        for i, byte in enumerate(raw):
            parser.feed(bytes([byte]))
            if i < len(raw) - 1:
                assert not parser.is_complete()

        assert parser.is_complete()
        resp = parser.response
        assert resp.status_code == 200
        assert resp.reason == "OK"
        assert resp.headers["content-type"] == "application/json; charset=utf-8"
        assert resp.headers.get_list("set-cookie") == ["session=abc", "tracking=xyz"]
        assert resp.json() == {"message": "hello world", "items": [1, 2, 3]}
        assert "charset=utf-8" in resp.headers["Content-Type"]
