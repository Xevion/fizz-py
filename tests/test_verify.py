"""Certificate + hostname verification against hermetic local TLS servers."""

import ssl

import pytest

import fizzpy


def test_untrusted_cert_is_rejected_by_default(self_signed_server):
    url, _ = self_signed_server
    # Default verify=True validates the chain against the system trust store,
    # which does not contain our freshly minted self-signed cert. A verification
    # failure raises ssl.SSLCertVerificationError, matching OpenSSL.
    with pytest.raises(ssl.SSLCertVerificationError) as excinfo:
        fizzpy.get(url)
    assert "fizz::" not in str(excinfo.value)


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
    with pytest.raises(ssl.SSLCertVerificationError) as excinfo:
        fizzpy.get(url, cafile=cafile)
    assert "hostname" in str(excinfo.value).lower()


def test_wrong_hostname_accepted_when_verification_disabled(ca_server):
    url, _cafile, body = ca_server("wrong.example")
    with fizzpy.Client(verify=False) as client:
        r = client.get(url)
    assert r.status_code == 200
    assert r.content == body
