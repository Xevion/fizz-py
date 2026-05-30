"""Redirect handling: the pure resolver plus end-to-end follows over TLS."""

import pytest

import fizzpy
from fizzpy._common import next_redirect, strip_body_headers


class TestNextRedirect:
    def test_non_redirect_status_returns_none(self):
        assert next_redirect("GET", "https://x/", 200, "https://y/") is None

    def test_redirect_without_location_returns_none(self):
        assert next_redirect("GET", "https://x/", 302, None) is None

    def test_absolute_location(self):
        assert next_redirect("GET", "https://x/a", 302, "https://y/b") == (
            "GET",
            "https://y/b",
        )

    def test_relative_location_is_resolved(self):
        assert next_redirect("GET", "https://x/a/b", 302, "/c") == (
            "GET",
            "https://x/c",
        )

    def test_303_forces_get(self):
        assert next_redirect("POST", "https://x/", 303, "/next") == ("GET", "https://x/next")

    def test_302_downgrades_post_to_get(self):
        assert next_redirect("POST", "https://x/", 302, "/next") == ("GET", "https://x/next")

    def test_307_preserves_method(self):
        assert next_redirect("POST", "https://x/", 307, "/next") == ("POST", "https://x/next")


def test_strip_body_headers_drops_framing():
    out = strip_body_headers({"Content-Type": "x", "X-Keep": "y", "Content-Length": "3"})
    assert out == {"X-Keep": "y"}


def _at(server, path: str) -> str:
    return server.url.rstrip("/") + path


def test_follows_single_redirect(local_server):
    r = fizzpy.get(_at(local_server, "/redirect"), verify=False)
    assert r.status_code == 200
    assert r.content == b"hello from local tls"
    assert r.url == local_server.url  # ended at "/"


def test_follows_redirect_chain(local_server):
    r = fizzpy.get(_at(local_server, "/chain/3"), verify=False)
    assert r.status_code == 200
    assert r.content == b"hello from local tls"


def test_redirect_not_followed_when_disabled(local_server):
    r = fizzpy.get(_at(local_server, "/redirect"), verify=False, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/"


def test_too_many_redirects_raises(local_server):
    with pytest.raises(fizzpy.TooManyRedirects):
        fizzpy.get(_at(local_server, "/loop"), verify=False, max_redirects=3)


def test_303_redirect_downgrades_post_to_get(local_server):
    r = fizzpy.request("POST", _at(local_server, "/redirect-303"), verify=False, body=b"x")
    assert r.content == b"GET"


def test_307_redirect_preserves_post(local_server):
    r = fizzpy.request("POST", _at(local_server, "/redirect-307"), verify=False, body=b"x")
    assert r.content == b"POST"
