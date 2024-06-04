import pytest
import fizzpy


@pytest.fixture
def client():
    return fizzpy.FizzClientContext()


def test_versions(client):
    client.setSupportedVersions([fizzpy.ProtocolVersion.tls_1_0])
    assert client.getSupportedVersions() == [fizzpy.ProtocolVersion.tls_1_0]

def test_ciphers(client):
    client.setSupportedCiphers([fizzpy.CipherSuite.TLS_AES_128_GCM_SHA256])
    assert client.getSupportedCiphers() == [fizzpy.CipherSuite.TLS_AES_128_GCM_SHA256]


def test_sig_schemes(client):
    pass


def test_supported_groups(client):
    pass


def test_shares(client):
    pass


def test_supported_psk_modes(client):
    pass


def test_supported_alpns(client):
    pass
