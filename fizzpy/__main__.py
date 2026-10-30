"""Command line: ``python -m fizzpy probe HOST...`` (also installed as ``fizzpy``)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence

from .probe import (
    NoPostQuantumSupport,
    Outcome,
    ProbeResult,
    Verdict,
    parse_target,
    probe_many,
)

# (column header, group name in ProbeResult.attempts)
_COLUMNS = (
    ("ML-KEM", "X25519MLKEM768"),
    ("x25519", "x25519"),
    ("P-256", "secp256r1"),
    ("P-384", "secp384r1"),
)
_CELL = {Outcome.ACCEPTED: "ok", Outcome.REJECTED: "rej", Outcome.FAILED: "FAIL"}
_COLOR = {
    Verdict.POST_QUANTUM: "32",
    Verdict.CLASSICAL_ONLY: "33",
    Verdict.PQ_BLOCKED: "31",
    Verdict.NO_TLS13: "31",
    Verdict.UNREACHABLE: "90",
    Verdict.ERROR: "31",
}


def _paint(text: str, code: str, *, enabled: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


def _cell(result: ProbeResult, group: str) -> str:
    for attempt in result.attempts:
        if attempt.offered == (group,):
            return _CELL[attempt.outcome]
    return "-"


def _row(result: ProbeResult) -> list[str]:
    target = result.host if result.port == 443 else f"{result.host}:{result.port}"
    note = result.error or ""
    return [
        target,
        result.verdict.value,
        result.preferred or "-",
        *(_cell(result, group) for _, group in _COLUMNS),
        note,
    ]


def _print_table(results: Sequence[ProbeResult], *, color: bool) -> None:
    header = ["HOST", "VERDICT", "PREFERRED", *(name for name, _ in _COLUMNS), ""]
    rows = [header, *(_row(r) for r in results)]
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    for i, row in enumerate(rows):
        cells: list[str] = []
        for j, text in enumerate(row):
            padded = text.ljust(widths[j])
            if i > 0 and j == 1:
                padded = _paint(padded, _COLOR[results[i - 1].verdict], enabled=color)
            cells.append(padded)
        print("  ".join(cells).rstrip())


def _print_detail(result: ProbeResult) -> None:
    where = f" ({result.address}, tcp {result.tcp_ms}ms)" if result.address else ""
    print(f"\n{result.host}:{result.port}{where} -> {result.verdict.value}")
    if result.error:
        print(f"  error: {result.error}")
    for attempt in (*result.attempts, result.default):
        if attempt is None:
            continue
        label = "default offer" if attempt is result.default else attempt.offered[0]
        line = f"  {label:<16} {attempt.outcome.value:<9} {attempt.elapsed_ms:>7}ms"
        if attempt.outcome is Outcome.ACCEPTED:
            line += f"  {attempt.group} {attempt.cipher} alpn={attempt.alpn}"
            line += f" cert={attempt.certificate}"
        elif attempt.alert:
            line += f"  alert={attempt.alert}"
        if attempt.detail:
            line += f"  {attempt.detail}"
        print(line)


def _read_targets(args: argparse.Namespace) -> list[str]:
    raw: list[str] = list(args.targets)
    if args.file:
        if args.file == "-":
            lines = sys.stdin.read().splitlines()
        else:
            with open(args.file, encoding="utf-8-sig") as handle:
                lines = handle.read().splitlines()
        raw += [line.split("#", 1)[0].strip() for line in lines]
    return [t for t in raw if t]


async def _probe_all(
    args: argparse.Namespace, targets: list[tuple[str, int]]
) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    async for result in probe_many(
        targets, concurrency=args.concurrency, timeout=args.timeout, sni=args.sni
    ):
        if args.json:
            print(json.dumps(result.to_dict()), flush=True)
        results.append(result)
    return results


def _cmd_probe(args: argparse.Namespace) -> int:
    try:
        # Dedup on the parsed target, so Example.com and example.com:443 are one.
        targets = list(dict.fromkeys(parse_target(t) for t in _read_targets(args)))
    except (OSError, ValueError) as exc:
        print(f"fizzpy: {exc}", file=sys.stderr)
        return 2
    if not targets:
        print("fizzpy: no targets given (pass hosts or --file)", file=sys.stderr)
        return 2

    try:
        results = asyncio.run(_probe_all(args, targets))
    except NoPostQuantumSupport as exc:
        print(f"fizzpy: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130

    if not args.json:
        order = {t: i for i, t in enumerate(targets)}
        results.sort(key=lambda r: order.get((r.host, r.port), len(order)))
        # Legacy Windows consoles print escape codes raw, so colour is POSIX-only.
        color = (
            sys.stdout.isatty()
            and sys.platform != "win32"
            and "NO_COLOR" not in os.environ
        )
        _print_table(results, color=color)
        if args.verbose:
            for result in results:
                _print_detail(result)

    if args.require_pq and any(r.verdict is not Verdict.POST_QUANTUM for r in results):
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fizzpy", description="Post-quantum TLS 1.3 tools built on Fizz."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "probe",
        help="check which TLS 1.3 key exchanges a server accepts",
        description=(
            "Offer one key-exchange group per connection and report which the server "
            "accepts. 'rej' means the server answered with a TLS alert; 'FAIL' means "
            "the connection broke without one (reset, close, timeout). Certificates "
            "are not validated."
        ),
    )
    p.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help="host, host:port, [v6]:port or https:// URL",
    )
    p.add_argument(
        "-f", "--file", help="read targets from FILE, one per line ('-' for stdin)"
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="print one JSON object per target as it finishes",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="show every handshake in detail"
    )
    p.add_argument(
        "-c", "--concurrency", type=int, default=16, help="hosts probed at once (16)"
    )
    p.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=5.0,
        help="seconds per connect/handshake (5)",
    )
    p.add_argument(
        "--sni",
        metavar="NAME",
        help="server name to send for every target (default: the host; none for IPs)",
    )
    p.add_argument(
        "--require-pq",
        action="store_true",
        help="exit 1 unless every target is post-quantum",
    )
    p.set_defaults(func=_cmd_probe)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "probe" and (args.concurrency < 1 or args.timeout <= 0):
        print("fizzpy: --concurrency and --timeout must be positive", file=sys.stderr)
        return 2
    # A certificate subject can hold characters the terminal's encoding lacks.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")
    try:
        return args.func(args)
    except BrokenPipeError:
        # The reader went away (`| head`); aim stdout at devnull so the
        # interpreter's exit-time flush does not raise again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1


if __name__ == "__main__":
    sys.exit(main())
