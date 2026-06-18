"""HTTPS through a forward proxy: the client tunnels, fizzpy does TLS over it.

Proxy support is entirely the HTTP client's job — urllib3/httpcore perform the
``CONNECT`` and hand fizzpy an already-tunnelled socket, so the Fizz handshake
rides over the tunnel transparently and fizzpy never sees the proxy. These tests
prove that pass-through (and that the request really traversed the proxy).
"""

import pytest

import fizzpy

requests = pytest.importorskip("requests")
from fizzpy.contrib.requests import FizzAdapter  # noqa: E402


def test_requests_reaches_https_host_through_proxy(local_server, connect_proxy):
    session = requests.Session()
    session.mount("https://", FizzAdapter(fizzpy.TlsConfig(verify=False)))
    r = session.get(
        local_server.url,
        verify=False,
        proxies={"https": connect_proxy.url},
    )
    assert r.status_code == 200
    assert r.text == "hello from local tls"
    # connects==0 would mean the request reached the host directly, not via the
    # proxy — so this is what actually proves the tunnel was used.
    assert connect_proxy.connects >= 1


def test_httpx_reaches_https_host_through_proxy(local_server, connect_proxy):
    httpx = pytest.importorskip("httpx")
    from fizzpy.contrib.httpx import FizzHTTPTransport

    transport = FizzHTTPTransport(
        fizzpy.TlsConfig(verify=False), proxy=connect_proxy.url
    )
    with httpx.Client(transport=transport) as client:
        r = client.get(local_server.url)
    assert r.status_code == 200
    assert r.text == "hello from local tls"
    assert connect_proxy.connects >= 1
