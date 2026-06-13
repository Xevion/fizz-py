"""Certificate + hostname verification against hermetic local TLS servers."""

import pytest

import fizzpy


def test_untrusted_cert_is_rejected_by_default(self_signed_server):
    url, _ = self_signed_server
    # Default verify=True validates the chain against the system trust store,
    # which does not contain our freshly minted self-signed cert.
    with pytest.raises(ConnectionError):
        fizzpy.get(url)


def test_verify_false_accepts_untrusted_cert(self_signed_server):
    url, body = self_signed_server
    with fizzpy.Client(verify=False) as client:
        r = client.get(url)
    assert r.status_code == 200
    assert r.content == body
    assert r.tls["version"] == "TLSv1.3"


def test_trusted_chain_with_matching_hostname_succeeds(ca_server):
    url, cafile, body = ca_server("localhost")
    with fizzpy.Client(verify=True, cafile=cafile) as client:
        r = client.get(url)
    assert r.status_code == 200
    assert r.content == body


def test_trusted_chain_with_wrong_hostname_is_rejected(ca_server):
    # The chain is trusted (CA in cafile), but the cert's SAN is wrong.example
    # while we connect to localhost — the hostname check must reject it.
    url, cafile, _ = ca_server("wrong.example")
    with pytest.raises(ConnectionError) as excinfo:
        fizzpy.get(url, cafile=cafile)
    assert "hostname" in str(excinfo.value).lower()


def test_wrong_hostname_accepted_when_verification_disabled(ca_server):
    url, _cafile, body = ca_server("wrong.example")
    with fizzpy.Client(verify=False) as client:
        r = client.get(url)
    assert r.status_code == 200
    assert r.content == body
