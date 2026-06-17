"""The httpx transport: httpx keeps its features, Fizz does the TLS."""

import pytest

import fizzpy

httpx = pytest.importorskip("httpx")
from fizzpy.contrib.httpx import FizzHTTPTransport  # noqa: E402


def _client(config: fizzpy.TlsConfig | None = None, **kwargs: object) -> "httpx.Client":
    return httpx.Client(transport=FizzHTTPTransport(config), **kwargs)


def test_get_over_self_signed(local_server):
    with _client(fizzpy.TlsConfig(verify=False)) as client:
        r = client.get(local_server.url)
    assert r.status_code == 200
    assert r.text == "hello from local tls"


def test_verifies_trusted_chain(ca_server):
    url, cafile, body = ca_server("localhost")
    with _client(fizzpy.TlsConfig(cafile=cafile)) as client:
        r = client.get(url)
    assert r.status_code == 200
    assert r.content == body


def test_rejects_wrong_hostname(ca_server):
    url, cafile, _ = ca_server("wrong.example")
    with (
        _client(fizzpy.TlsConfig(cafile=cafile)) as client,
        pytest.raises(httpx.HTTPError) as excinfo,
    ):
        client.get(url)
    assert "hostname" in str(excinfo.value).lower()


def test_rejects_untrusted_chain_by_default(local_server):
    # Default config verifies against certifi, which does not trust the cert.
    with _client() as client, pytest.raises(httpx.HTTPError):
        client.get(local_server.url)


def test_redirects_still_followed(local_server):
    # An httpx feature (redirect following) works unchanged over Fizz TLS.
    with _client(fizzpy.TlsConfig(verify=False), follow_redirects=True) as client:
        r = client.get(local_server.url + "redirect")
    assert r.status_code == 200
    assert r.text == "hello from local tls"
    assert r.history
    assert r.history[0].status_code == 302


def test_connection_is_reused(local_server):
    # httpcore keep-alive reuse works through the TlsSocket (validates fileno()).
    with _client(fizzpy.TlsConfig(verify=False)) as client:
        client.get(local_server.url)
        client.get(local_server.url)
    assert local_server.connections == 1


def test_rejects_unsupported_kwargs():
    with pytest.raises(TypeError):
        FizzHTTPTransport(verify=False)
    with pytest.raises(TypeError):
        FizzHTTPTransport(cert="x")
    with pytest.raises(ValueError):
        FizzHTTPTransport(http2=True)


@pytest.mark.network
def test_negotiates_post_quantum_against_cloudflare():
    with (
        _client() as client,
        client.stream("GET", "https://www.cloudflare.com") as r,
    ):
        assert r.status_code == 200
        sock = r.extensions["network_stream"].get_extra_info("socket")
        assert sock.tls["group_code"] == 4588
