import pytest
import fizzpy


@pytest.fixture
def client():
    return fizzpy.FizzClientContext()


def test_versions(client):
    client.setSupportedVersions([fizzpy.ProtocolVersion.tls_1_0])
    assert client.getSupportedVersions() == [fizzpy.ProtocolVersion.tls_1_0]

def test_ciphers(client):
    return


def test_sig_schemes(client):
    return


def test_supported_groups(client):
    return


def test_shares(client):
    return


def test_supported_psk_modes(client):
    return


def test_supported_alpns(client):
    return
