"""The post-quantum readiness probe, against local servers with known behaviour.

None of the local servers speak ML-KEM (the stdlib's OpenSSL predates it), so the
post-quantum-positive path lives in the network tests at the bottom.
"""

import asyncio
import json
from urllib.parse import urlsplit

import pytest

import fizzpy.probe as probe_module
from fizzpy import supports_post_quantum
from fizzpy.probe import (
    Attempt,
    NoPostQuantumSupport,
    Outcome,
    Verdict,
    _explain_error,  # pyright: ignore[reportPrivateUsage]
    _server_name,  # pyright: ignore[reportPrivateUsage]
    _verdict,  # pyright: ignore[reportPrivateUsage]
    parse_target,
    probe,
    probe_many,
)

pytestmark = pytest.mark.skipif(
    not supports_post_quantum(), reason="build has no post-quantum support"
)


def _port(url: str) -> int:
    port = urlsplit(url).port
    assert port is not None
    return port


def _run(coro):
    return asyncio.run(coro)


def test_classical_server_is_classical_only(self_signed_server):
    url, _ = self_signed_server
    r = _run(probe("127.0.0.1", _port(url), timeout=5))

    assert r.verdict is Verdict.CLASSICAL_ONLY
    assert r.address == "127.0.0.1"
    pq, *classical = r.attempts
    assert pq.offered == ("X25519MLKEM768",)
    assert pq.outcome is Outcome.REJECTED
    assert pq.alert == "handshake_failure"
    assert "x25519" in r.accepted_groups
    assert "X25519MLKEM768" not in r.accepted_groups
    assert all(a.outcome is Outcome.ACCEPTED for a in classical[:2])
    # A stock client falls back to x25519 on this server.
    assert r.default is not None
    assert r.default.outcome is Outcome.ACCEPTED
    assert r.preferred == "x25519"
    assert r.default.version == "TLSv1.3"
    assert r.default.group == "x25519"


def test_tls12_only_server_is_no_tls13(tls12_server):
    r = _run(probe("127.0.0.1", _port(tls12_server.url), timeout=5))

    assert r.verdict is Verdict.NO_TLS13
    assert {a.alert for a in r.attempts} == {"protocol_version"}
    assert r.accepted_groups == []


def test_closed_port_is_unreachable():
    r = _run(probe("127.0.0.1", 1, timeout=2))

    assert r.verdict is Verdict.UNREACHABLE
    assert r.address is None
    assert r.error == "connect: connection refused"
    assert r.attempts == ()


@pytest.mark.parametrize(
    ("reply", "detail"),
    [
        (b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n", "not a TLS server"),
        (b"", "connection closed"),
    ],
    ids=["plain-http", "closes-immediately"],
)
def test_non_tls_port_is_error(scripted_server, reply, detail):
    port = scripted_server(reply)
    r = _run(probe("127.0.0.1", port, timeout=3))

    assert r.verdict is Verdict.ERROR
    assert {a.outcome for a in r.attempts} == {Outcome.FAILED}
    assert {a.detail for a in r.attempts} == {detail}
    assert r.error == detail


@pytest.mark.parametrize(
    ("action", "detail"), [("reset", "connection reset"), ("drop", "timeout")]
)
def test_pq_sized_hello_that_breaks_connection_is_pq_blocked(
    self_signed_server, hello_limit_proxy, action, detail
):
    url, _ = self_signed_server
    port = hello_limit_proxy(_port(url), action=action)

    r = _run(probe("127.0.0.1", port, timeout=1))

    assert r.verdict is Verdict.PQ_BLOCKED
    pq = r.attempts[0]
    assert pq.outcome is Outcome.FAILED
    assert pq.detail == detail
    assert pq.alert is None
    # Classical handshakes pass through the same middlebox fine.
    assert "x25519" in r.accepted_groups
    # The stock client sends the big hello too, so it is broken as well.
    assert r.default is not None
    assert r.default.outcome is Outcome.FAILED


def _attempt(group: str, outcome: Outcome, alert: str | None = None) -> Attempt:
    return Attempt(offered=(group,), outcome=outcome, elapsed_ms=1.0, alert=alert)


ACC, REJ, FAIL = Outcome.ACCEPTED, Outcome.REJECTED, Outcome.FAILED
NO_GROUP = "handshake_failure"


@pytest.mark.parametrize(
    ("pq", "classical", "expected"),
    [
        ((ACC, None), [(ACC, None), (REJ, NO_GROUP)], Verdict.POST_QUANTUM),
        ((ACC, None), [(FAIL, None)] * 3, Verdict.POST_QUANTUM),
        ((REJ, NO_GROUP), [(ACC, None), (REJ, NO_GROUP)], Verdict.CLASSICAL_ONLY),
        ((REJ, "insufficient_security"), [(ACC, None)], Verdict.CLASSICAL_ONLY),
        ((FAIL, None), [(REJ, NO_GROUP), (ACC, None)], Verdict.PQ_BLOCKED),
        # An alert that is not "no common group" is a server bug, not a rejection.
        ((REJ, "internal_error"), [(ACC, None)], Verdict.PQ_BLOCKED),
        ((REJ, "illegal_parameter"), [(ACC, None)], Verdict.PQ_BLOCKED),
        ((REJ, NO_GROUP), [(REJ, "protocol_version")] * 3, Verdict.NO_TLS13),
        ((REJ, NO_GROUP), [(REJ, NO_GROUP), (FAIL, None)], Verdict.ERROR),
        # Every offer refused over the server name says nothing about groups.
        ((REJ, "unrecognized_name"), [(REJ, "unrecognized_name")] * 3, Verdict.ERROR),
        ((FAIL, None), [(FAIL, None)] * 3, Verdict.ERROR),
    ],
)
def test_verdict_table(pq, classical, expected):
    attempts = [_attempt("X25519MLKEM768", *pq)]
    attempts += [_attempt("x25519", *c) for c in classical]
    assert _verdict(attempts) is expected


def test_unrecognized_name_everywhere_points_at_sni():
    attempts = tuple(
        Attempt(offered=("x",), outcome=REJ, elapsed_ms=1.0, alert="unrecognized_name")
        for _ in range(4)
    )

    assert "try --sni" in _explain_error(attempts)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("example.com", "example.com"),
        ("bücher.example", "xn--bcher-kva.example"),
        ("1.2.3.4", ""),
        ("2606:4700::1111", ""),
    ],
)
def test_server_name_is_ascii_and_empty_for_ip_literals(host, expected):
    assert _server_name(host) == expected


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("example.com", ("example.com", 443)),
        ("example.com:8443", ("example.com", 8443)),
        ("Example.COM", ("example.com", 443)),
        ("https://example.com/path?q=1", ("example.com", 443)),
        ("https://example.com:9443", ("example.com", 9443)),
        ("1.2.3.4", ("1.2.3.4", 443)),
        ("1.2.3.4:444", ("1.2.3.4", 444)),
        ("2606:4700::1111", ("2606:4700::1111", 443)),
        ("[2606:4700::1111]:8443", ("2606:4700::1111", 8443)),
        ("  example.com  ", ("example.com", 443)),
        ("Example.com.", ("example.com", 443)),
        ("bücher.example:8443", ("bücher.example", 8443)),
    ],
)
def test_parse_target(target, expected):
    assert parse_target(target) == expected


@pytest.mark.parametrize(
    "target",
    [
        "",
        "http://example.com",
        "example.com:notaport",
        "example.com:99999",
        "example.com:0",
        "example.com:",
        "user@example.com",
        ":443",
        "a" * 64 + ".com",
    ],
)
def test_parse_target_rejects(target):
    with pytest.raises(ValueError):
        parse_target(target)


def test_result_serializes_to_json(self_signed_server):
    url, _ = self_signed_server
    r = _run(probe("127.0.0.1", _port(url), timeout=5))

    data = json.loads(json.dumps(r.to_dict()))
    assert data["verdict"] == "classical-only"
    assert data["attempts"][0]["outcome"] == "rejected"
    assert data["default"]["outcome"] == "accepted"
    assert data["port"] == _port(url)


def test_probe_many_streams_every_target(self_signed_server, tls12_server):
    url, _ = self_signed_server
    targets = [
        f"127.0.0.1:{_port(url)}",
        f"127.0.0.1:{_port(tls12_server.url)}",
        "127.0.0.1:1",
    ]

    async def collect():
        return {
            r.port: r.verdict
            async for r in probe_many(targets, concurrency=2, timeout=3)
        }

    assert _run(collect()) == {
        _port(url): Verdict.CLASSICAL_ONLY,
        _port(tls12_server.url): Verdict.NO_TLS13,
        1: Verdict.UNREACHABLE,
    }


def test_probe_many_rejects_a_bad_target_before_connecting(self_signed_server):
    url, _ = self_signed_server

    async def collect():
        return [r async for r in probe_many([f"127.0.0.1:{_port(url)}", "http://nope"])]

    with pytest.raises(ValueError, match="TLS only"):
        _run(collect())


@pytest.mark.network
@pytest.mark.parametrize("host", ["www.cloudflare.com", "www.google.com"])
def test_live_post_quantum_host(host):
    r = _run(probe(host, timeout=10))

    assert r.verdict is Verdict.POST_QUANTUM
    assert "X25519MLKEM768" in r.accepted_groups
    assert r.preferred == "X25519MLKEM768"
    assert r.attempts[0].group == "X25519MLKEM768"
    assert r.attempts[0].certificate


def test_unencodable_hostname_is_unreachable_not_a_crash():
    # Bypasses parse_target, which would reject the name up front.
    r = _run(probe("a" * 64 + ".com", timeout=2))

    assert r.verdict is Verdict.UNREACHABLE
    assert r.error is not None
    assert r.error.startswith("dns:")


def test_one_failing_host_does_not_end_a_scan(self_signed_server, monkeypatch):
    url, _ = self_signed_server
    real = probe_module.probe

    async def flaky(host, port, **kwargs):
        if port == 2:
            raise ValueError("boom")
        return await real(host, port, **kwargs)

    monkeypatch.setattr(probe_module, "probe", flaky)

    async def collect():
        targets = [f"127.0.0.1:{_port(url)}", "127.0.0.1:2"]
        return {r.port: r async for r in probe_many(targets, timeout=3)}

    results = _run(collect())
    assert results[2].verdict is Verdict.ERROR
    assert results[2].error == "ValueError: boom"
    assert results[_port(url)].verdict is Verdict.CLASSICAL_ONLY


def test_leaving_a_scan_early_leaves_no_tasks_behind(self_signed_server):
    url, _ = self_signed_server

    async def first_then_stop():
        targets = [f"127.0.0.1:{_port(url)}"] * 3 + ["127.0.0.1:1"] * 3
        scan = probe_many(targets, concurrency=2, timeout=3)
        async for _ in scan:
            break
        await scan.aclose()
        return len(asyncio.all_tasks())

    assert _run(first_then_stop()) == 1  # only the coroutine running this check


def test_probe_refuses_when_the_build_has_no_post_quantum(monkeypatch):
    monkeypatch.setattr(probe_module, "supports_post_quantum", lambda: False)

    with pytest.raises(NoPostQuantumSupport, match="no post-quantum support"):
        _run(probe("127.0.0.1", 1))
