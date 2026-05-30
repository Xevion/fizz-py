"""Connection reuse (HTTP/1.1 keep-alive) for the sync and async clients.

The local server counts accepted TCP connections, so reuse is observable:
N requests over one persistent connection means the count stays at 1.
"""

import asyncio

import fizzpy
from fizzpy.aio import AsyncClient


def _at(server, path: str) -> str:
    return server.url.rstrip("/") + path


def test_sequential_requests_reuse_one_connection(local_server):
    with fizzpy.Client(verify=False) as client:
        for _ in range(3):
            assert client.get(local_server.url).status_code == 200
    assert local_server.connections == 1


def test_close_drops_the_pool(local_server):
    client = fizzpy.Client(verify=False)
    client.get(local_server.url)
    client.close()
    client.get(local_server.url)  # pool empty → must reconnect
    assert local_server.connections == 2


def test_redirect_chain_reuses_one_connection(local_server):
    # Four hops (/chain/3 → /chain/2 → /chain/1 → /) to the same host should
    # all ride a single pooled connection.
    with fizzpy.Client(verify=False) as client:
        r = client.get(_at(local_server, "/chain/3"))
    assert r.status_code == 200
    assert local_server.connections == 1


def test_async_sequential_requests_reuse_one_connection(local_server):
    async def main():
        async with AsyncClient(verify=False) as client:
            for _ in range(3):
                assert (await client.get(local_server.url)).status_code == 200

    asyncio.run(main())
    assert local_server.connections == 1
