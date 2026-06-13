"""Live TLS integration tests. Deselect offline with ``-m "not network"``."""

import asyncio

import pytest

import fizzpy
from fizzpy.aio import AsyncClient

pytestmark = pytest.mark.network

HOST = "https://example.com"


def test_sync_get():
    r = fizzpy.get(HOST)
    assert r.status_code == 200
    assert r.http_version == "HTTP/1.1"
    assert "text/html" in r.headers.get("content-type", "")
    assert b"<html" in r.content.lower() or b"<!doctype" in r.content.lower()


def test_negotiated_tls_parameters():
    r = fizzpy.get(HOST)
    tls = r.tls
    assert tls["version"] == "TLSv1.3"
    assert tls["sni"] == "example.com"
    assert tls["group"]  # some key-exchange group was negotiated
    assert tls["cipher"].startswith("TLS_")


def test_post_quantum_negotiated_by_default():
    # Against a server that supports it (Cloudflare), the default config must
    # negotiate the standardized hybrid ML-KEM group (codepoint 4588).
    r = fizzpy.get("https://www.cloudflare.com")
    assert r.status_code == 200
    assert r.tls["group"] == "X25519MLKEM768"
    assert r.tls["group_code"] == 4588


def test_forcing_post_quantum_group():
    c = fizzpy.Client(groups=[fizzpy.NamedGroup.x25519_mlkem768])
    r = c.get("https://www.google.com")
    assert r.status_code == 200
    assert r.tls["group_code"] == 4588


def test_classical_group_still_works():
    c = fizzpy.Client(groups=[fizzpy.NamedGroup.x25519])
    r = c.get("https://www.cloudflare.com")
    assert r.status_code == 200
    assert r.tls["group"] == "x25519"


def test_async_concurrent_requests():
    async def main():
        async with AsyncClient() as client:
            return await asyncio.gather(
                client.get(HOST),
                client.get("https://www.cloudflare.com"),
            )

    r1, r2 = asyncio.run(main())
    assert r1.status_code == 200
    assert r2.status_code == 200
