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


def test_async_concurrent_requests():
    async def main():
        async with AsyncClient() as client:
            results = await asyncio.gather(
                client.get(HOST),
                client.get("https://www.cloudflare.com"),
            )
            return results

    r1, r2 = asyncio.run(main())
    assert r1.status_code == 200
    assert r2.status_code == 200
