"""The requests adapter: requests keeps its features, Fizz does the TLS."""

import pytest

import fizzpy

requests = pytest.importorskip("requests")
from fizzpy.contrib.requests import FizzAdapter  # noqa: E402


def _session(config: fizzpy.TlsConfig | None = None) -> requests.Session:
    session = requests.Session()
    session.mount("https://", FizzAdapter(config))
    return session


def test_get_over_self_signed(local_server):
    session = _session()
    r = session.get(local_server.url, verify=False)
    assert r.status_code == 200
    assert r.text == "hello from local tls"


def test_verifies_trusted_chain(ca_server):
    url, cafile, body = ca_server("localhost")
    session = _session()
    r = session.get(url, verify=cafile)
    assert r.status_code == 200
    assert r.content == body


def test_rejects_wrong_hostname(ca_server):
    url, cafile, _ = ca_server("wrong.example")
    session = _session()
    with pytest.raises(requests.exceptions.RequestException) as excinfo:
        session.get(url, verify=cafile)
    assert "hostname" in str(excinfo.value).lower()


def test_rejects_untrusted_chain_by_default(local_server):
    session = _session()
    with pytest.raises(requests.exceptions.RequestException):
        session.get(local_server.url)  # certifi does not trust the self-signed cert


def test_redirects_still_followed(local_server):
    # A requests feature (redirect following) works unchanged over Fizz TLS.
    session = _session()
    r = session.get(local_server.url + "redirect", verify=False)
    assert r.status_code == 200
    assert r.text == "hello from local tls"
    assert r.history
    assert r.history[0].status_code == 302


def test_connection_is_reused(local_server):
    # urllib3 keep-alive reuse works through the TlsSocket (validates fileno()).
    session = _session()
    session.get(local_server.url, verify=False)
    session.get(local_server.url, verify=False)
    assert local_server.connections == 1


@pytest.mark.network
def test_negotiates_post_quantum_against_cloudflare():
    session = _session()
    r = session.get("https://www.cloudflare.com", stream=True)
    try:
        assert r.status_code == 200
        assert r.raw.connection.sock.tls["group_code"] == 4588
    finally:
        r.close()
