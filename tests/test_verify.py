"""Certificate verification against a hermetic local self-signed TLS server."""

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
