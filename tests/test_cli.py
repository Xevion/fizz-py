"""``fizzpy probe`` end to end, against local servers (no network)."""

import json
from urllib.parse import urlsplit

import pytest

import fizzpy.__main__ as cli
from fizzpy import supports_post_quantum
from fizzpy.__main__ import main
from fizzpy.probe import ProbeResult, Verdict

pytestmark = pytest.mark.skipif(
    not supports_post_quantum(), reason="build has no post-quantum support"
)


def _target(url: str) -> str:
    return f"127.0.0.1:{urlsplit(url).port}"


def test_table_lists_each_target_in_input_order(
    self_signed_server, tls12_server, capsys
):
    classical, _ = self_signed_server

    # The closed port fails fastest, so it completes first but must print last.
    closed = "127.0.0.1:1"
    code = main(
        ["probe", _target(tls12_server.url), _target(classical), closed, "-t", "3"]
    )

    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    assert lines[0].split() == [
        "HOST",
        "VERDICT",
        "PREFERRED",
        "ML-KEM",
        "x25519",
        "P-256",
        "P-384",
    ]
    assert lines[1].split()[:2] == [_target(tls12_server.url), "no-tls13"]
    assert lines[2].split() == [
        _target(classical),
        "classical-only",
        "x25519",
        "rej",
        "ok",
        "ok",
        "ok",
    ]
    assert lines[3].split()[:2] == [closed, "unreachable"]


def test_json_is_one_object_per_target(self_signed_server, capsys):
    url, _ = self_signed_server

    code = main(["probe", "--json", _target(url), "127.0.0.1:1", "-t", "3"])

    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert code == 0
    assert {r["port"]: r["verdict"] for r in rows} == {
        urlsplit(url).port: "classical-only",
        1: "unreachable",
    }


def test_verbose_shows_each_handshake(self_signed_server, capsys):
    url, _ = self_signed_server

    main(["probe", "-v", _target(url), "-t", "3"])

    out = capsys.readouterr().out
    assert "alert=handshake_failure" in out
    assert "default offer" in out
    assert "(127.0.0.1, tcp " in out


def test_targets_file_skips_comments_blanks_and_duplicates(
    self_signed_server, tmp_path, capsys
):
    url, _ = self_signed_server
    target = _target(url)
    listing = tmp_path / "targets.txt"
    listing.write_text(f"# header\n\n{target}  # inline\n{target}\n")

    main(["probe", "--json", "-f", str(listing), "-t", "3"])

    assert len(capsys.readouterr().out.splitlines()) == 1


def test_require_pq_fails_unless_every_target_is_post_quantum(self_signed_server):
    url, _ = self_signed_server

    assert main(["probe", _target(url), "-t", "3"]) == 0
    assert main(["probe", _target(url), "--require-pq", "-t", "3"]) == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["probe"],
        ["probe", "http://example.com"],
        ["probe", "-f", "/nonexistent/targets.txt"],
        ["probe", "example.com", "--concurrency", "0"],
        ["probe", "example.com", "--timeout", "0"],
    ],
    ids=[
        "no-targets",
        "non-tls-url",
        "missing-file",
        "zero-concurrency",
        "zero-timeout",
    ],
)
def test_usage_errors_exit_2(argv, capsys):
    assert main(argv) == 2
    assert capsys.readouterr().err.startswith("fizzpy: ")


def test_require_pq_passes_when_every_target_is_post_quantum(monkeypatch):
    async def all_post_quantum(targets, **kwargs):
        for host, port in targets:
            yield ProbeResult(host, port, Verdict.POST_QUANTUM)

    monkeypatch.setattr(cli, "probe_many", all_post_quantum)

    assert main(["probe", "example.com", "--require-pq"]) == 0


def test_build_without_post_quantum_exits_2(monkeypatch, capsys):
    from fizzpy import probe as probe_module

    monkeypatch.setattr(probe_module, "supports_post_quantum", lambda: False)

    assert main(["probe", "127.0.0.1:1"]) == 2
    assert "no post-quantum support" in capsys.readouterr().err


def test_sni_is_passed_to_every_probe(monkeypatch):
    seen = {}

    async def record(targets, **kwargs):
        seen.update(kwargs)
        for host, port in targets:
            yield ProbeResult(host, port, Verdict.UNREACHABLE)

    monkeypatch.setattr(cli, "probe_many", record)

    assert main(["probe", "1.2.3.4", "--sni", "example.com"]) == 0
    assert seen["sni"] == "example.com"
