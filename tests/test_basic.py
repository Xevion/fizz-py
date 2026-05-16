"""Unit tests that need no network: URL parsing and low-level Fizz config."""

import pytest

import fizzpy
from fizzpy import _core
from fizzpy._common import parse_url


class TestParseUrl:
    def test_https_defaults_to_443(self):
        target = parse_url("https://example.com/path?q=1")
        assert target.host == "example.com"
        assert target.port == 443
        assert target.path == "/path?q=1"

    def test_explicit_port(self):
        assert parse_url("https://example.com:8443/").port == 8443

    def test_empty_path_becomes_root(self):
        assert parse_url("https://example.com").path == "/"

    def test_http_is_rejected(self):
        with pytest.raises(ValueError):
            parse_url("http://example.com")

    def test_missing_host_is_rejected(self):
        with pytest.raises(ValueError):
            parse_url("https:///path")


class TestFizzClientContext:
    @pytest.fixture
    def ctx(self):
        return _core.FizzClientContext()

    def test_versions_roundtrip(self, ctx):
        ctx.setSupportedVersions([_core.ProtocolVersion.tls_1_3])
        assert ctx.getSupportedVersions() == [_core.ProtocolVersion.tls_1_3]

    def test_ciphers_roundtrip(self, ctx):
        ctx.setSupportedCiphers([_core.CipherSuite.TLS_AES_128_GCM_SHA256])
        assert ctx.getSupportedCiphers() == [_core.CipherSuite.TLS_AES_128_GCM_SHA256]

    def test_alpns_roundtrip(self, ctx):
        ctx.setSupportedAlpns(["h2", "http/1.1"])
        assert ctx.getSupportedAlpns() == ["h2", "http/1.1"]


class TestNamedGroups:
    def test_classical_groups_present(self):
        assert _core.NamedGroup.x25519 is not None
        assert _core.NamedGroup.secp256r1 is not None

    def test_post_quantum_group_present(self):
        # The standardized hybrid ML-KEM group (codepoint 4588) is the
        # project's differentiator.
        assert int(_core.NamedGroup.x25519_mlkem768.value) == 4588


def test_default_groups_lead_with_post_quantum():
    from fizzpy._common import DEFAULT_GROUPS

    assert DEFAULT_GROUPS[0] == _core.NamedGroup.x25519_mlkem768
    assert _core.NamedGroup.x25519 in DEFAULT_GROUPS


def test_public_api_surface():
    for name in ("Client", "get", "post", "request", "Response"):
        assert hasattr(fizzpy, name)
