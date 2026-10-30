"""Post-quantum readiness probe: which TLS 1.3 key exchanges does a server accept?

A normal handshake only shows what a server *chose* from your offer, and a server
that prefers x25519 over ML-KEM looks the same as one that cannot do ML-KEM at
all. The probe settles it by offering one group per connection (the hybrid
``X25519MLKEM768`` and a few classical ones) and recording whether the server
accepts it, rejects it with a TLS alert, or breaks the connection. That last case
is the one that bites real deployments: a middlebox or an old stack that chokes
on the larger post-quantum ClientHello resets a connection that works fine
classically.

    import asyncio
    from fizzpy.probe import probe

    result = asyncio.run(probe("www.cloudflare.com"))
    print(result.verdict)             # Verdict.POST_QUANTUM
    print(result.accepted_groups)     # ['X25519MLKEM768', 'x25519', ...]

Certificates are never validated: the probe measures key-exchange support, not
trust, and a certificate check happens after the exchange it is observing.
"""

from __future__ import annotations

import asyncio
import errno
import ipaddress
import socket
import time
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlsplit

from . import _core  # pyright: ignore[reportPrivateUsage]  # our own extension module
from ._common import supports_post_quantum
from ._tls import TlsConfig, handshake_async

__all__ = [
    "CLASSICAL_GROUPS",
    "PQ_GROUP",
    "PQ_NAME",
    "Attempt",
    "NoPostQuantumSupport",
    "Outcome",
    "ProbeResult",
    "Verdict",
    "parse_target",
    "probe",
    "probe_many",
]

PQ_GROUP = _core.NamedGroup.x25519_mlkem768
CLASSICAL_GROUPS = (
    _core.NamedGroup.x25519,
    _core.NamedGroup.secp256r1,
    _core.NamedGroup.secp384r1,
)
# Fizz can only run key exchange for these; the pure ML-KEM and P-256 hybrid
# groups are not implemented in its crypto backend, so they cannot be probed.
_PROBE_GROUPS = (PQ_GROUP, *CLASSICAL_GROUPS)
_DEFAULT_OFFER = (PQ_GROUP, _core.NamedGroup.x25519)
# The spelling Fizz reports for a negotiated group, so offered and negotiated
# groups compare equal.
_NAMES = {
    _core.NamedGroup.x25519_mlkem768: "X25519MLKEM768",
    _core.NamedGroup.x25519: "x25519",
    _core.NamedGroup.secp256r1: "secp256r1",
    _core.NamedGroup.secp384r1: "secp384r1",
}
PQ_NAME = _NAMES[PQ_GROUP]
PROBE_ALPN = ("h2", "http/1.1")

# Slack past the handshake deadline the core already enforces, so a stuck
# connection can never hang a scan.
_GUARD_SECONDS = 2.0

_UNREACHABLE = frozenset({errno.ENETUNREACH, errno.EHOSTUNREACH})


class NoPostQuantumSupport(RuntimeError):
    """This build of fizzpy cannot do ML-KEM, so it cannot probe for it."""


class Outcome(str, Enum):
    """What happened to one handshake attempt."""

    ACCEPTED = "accepted"
    """The server completed the handshake with the offered group."""
    REJECTED = "rejected"
    """The server answered with a TLS alert (it understood and said no)."""
    FAILED = "failed"
    """No alert: a timeout, reset, early close, or a peer that is not TLS."""


class Verdict(str, Enum):
    """The overall post-quantum readiness of a host."""

    POST_QUANTUM = "post-quantum"
    """Completes a handshake with the X25519MLKEM768 hybrid."""
    CLASSICAL_ONLY = "classical-only"
    """TLS 1.3 works, but the server rejects the post-quantum group."""
    PQ_BLOCKED = "pq-blocked"
    """Classical handshakes work, but the post-quantum ClientHello breaks the
    handshake (reset, close, timeout, or an alert other than "no common group")
    instead of being answered. Server, middlebox and path are indistinguishable."""
    NO_TLS13 = "no-tls13"
    """Every offer drew a "no TLS 1.3 / no common group" alert."""
    UNREACHABLE = "unreachable"
    """No TCP connection could be made (DNS, refused, timeout)."""
    ERROR = "error"
    """TCP connected but no handshake got a TLS answer, e.g. not a TLS port."""


@dataclass(frozen=True)
class Attempt:
    """One handshake: the groups offered and how the server responded."""

    offered: tuple[str, ...]
    outcome: Outcome
    elapsed_ms: float
    alert: str | None = None
    detail: str | None = None
    group: str | None = None
    version: str | None = None
    cipher: str | None = None
    alpn: str | None = None
    certificate: str | None = None


@dataclass(frozen=True)
class ProbeResult:
    """Everything learned about one host."""

    host: str
    port: int
    verdict: Verdict
    address: str | None = None
    tcp_ms: float | None = None
    error: str | None = None
    attempts: tuple[Attempt, ...] = ()
    default: Attempt | None = None
    """The handshake a stock client would make, offering ML-KEM then x25519."""

    @property
    def accepted_groups(self) -> list[str]:
        """Names of the groups the server completed a handshake with."""
        return [a.offered[0] for a in self.attempts if a.outcome is Outcome.ACCEPTED]

    @property
    def preferred(self) -> str | None:
        """The group a stock client ends up with, if its handshake succeeded."""
        return self.default.group if self.default else None

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready dict (enums as their string values)."""
        out = asdict(self)
        out["verdict"] = self.verdict.value
        for attempt in (*out["attempts"], out["default"]):
            if attempt is not None:
                attempt["outcome"] = attempt["outcome"].value
        return out


def parse_target(target: str, default_port: int = 443) -> tuple[str, int]:
    """Split ``host``, ``host:port``, ``[v6]:port`` or an ``https://`` URL.

    The host is lowercased and loses any trailing dot. Raises ``ValueError`` for
    an empty or unencodable host, user info, a missing or out-of-range port, or
    a non-https scheme.
    """
    text = target.strip()
    try:
        ipaddress.ip_address(text)
    except ValueError:
        pass
    else:
        return text, default_port
    parts = urlsplit(text if "://" in text else f"//{text}")
    if parts.scheme not in ("", "https"):
        raise ValueError(f"fizzpy probes TLS only, got {parts.scheme!r}: {target!r}")
    if parts.username is not None or parts.password is not None:
        raise ValueError(f"unexpected user info in {target!r}")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise ValueError(f"no host in {target!r}")
    try:
        host.encode("idna")
    except UnicodeError:
        raise ValueError(f"invalid hostname in {target!r}") from None
    if parts.netloc.endswith(":"):
        raise ValueError(f"empty port in {target!r}")
    port = parts.port if parts.port is not None else default_port
    if not 1 <= port <= 65535:
        raise ValueError(f"port out of range in {target!r}")
    return host, port


def _server_name(host: str) -> str:
    """The SNI for ``host``: ASCII (IDNA), or empty (none sent) for an IP literal."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host.encode("idna").decode("ascii")
    return ""


_ERRNO_REASONS = (
    (ConnectionRefusedError, "connection refused"),
    (ConnectionResetError, "connection reset"),
    (ConnectionAbortedError, "connection aborted"),
    (asyncio.TimeoutError, "timeout"),
    (TimeoutError, "timeout"),
)


def _reason(exc: BaseException) -> str:
    """A short, platform-independent description of a failure without an alert."""
    for kind, reason in _ERRNO_REASONS:
        if isinstance(exc, kind):
            return reason
    if isinstance(exc, socket.gaierror):
        return "name not resolved"
    if isinstance(exc, OSError) and exc.errno in _UNREACHABLE:
        return "network unreachable"
    text = str(exc)
    lowered = text.lower()
    if "timed out" in lowered:
        return "timeout"
    if "reset by peer" in lowered:
        return "connection reset"
    if "end of file" in lowered:
        return "connection closed"
    if "plaintext content type" in lowered:
        return "not a TLS server"
    return text.removeprefix("handshake failed: ")


def _classify(exc: BaseException) -> tuple[Outcome, str | None, str | None]:
    """Map a handshake exception to ``(outcome, alert, detail)``."""
    alert: str | None = getattr(exc, "fizz_alert", None)
    if alert is not None and getattr(exc, "fizz_alert_remote", False):
        return Outcome.REJECTED, alert, None
    return Outcome.FAILED, alert, _reason(exc)


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


async def _connect(info: tuple[Any, ...], timeout: float) -> socket.socket:
    family, type_, proto, _, sockaddr = info
    sock = socket.socket(family, type_, proto)
    sock.settimeout(0.0)  # non-blocking, for sock_connect
    try:
        await asyncio.wait_for(
            asyncio.get_running_loop().sock_connect(sock, sockaddr), timeout
        )
    except BaseException:
        sock.close()
        raise
    return sock


async def _handshake(
    sock: socket.socket,
    sni: str,
    alpn: Sequence[str],
    groups: Sequence[_core.NamedGroup],
    timeout: float,
) -> Attempt:
    """Handshake offering exactly ``groups``; always closes ``sock``."""
    offered = tuple(_NAMES[g] for g in groups)
    config = TlsConfig(verify=False, alpn=alpn, groups=groups, timeout=timeout)
    start = time.perf_counter()
    conn: _core.TlsConnection | None = None
    try:
        conn = await asyncio.wait_for(
            handshake_async(sock, sni, config), timeout + _GUARD_SECONDS
        )
        n = conn.negotiated()
        if len(offered) == 1 and n["group"] != offered[0]:
            return Attempt(
                offered=offered,
                outcome=Outcome.FAILED,
                elapsed_ms=_elapsed_ms(start),
                detail=f"negotiated {n['group']} instead",
            )
        return Attempt(
            offered=offered,
            outcome=Outcome.ACCEPTED,
            elapsed_ms=_elapsed_ms(start),
            group=str(n["group"]),
            version=str(n["version"]),
            cipher=str(n["cipher"]),
            alpn=str(n["alpn"]) or None,
            certificate=str(n["peer_cert"]) or None,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        outcome, alert, detail = _classify(exc)
        return Attempt(
            offered=offered,
            outcome=outcome,
            elapsed_ms=_elapsed_ms(start),
            alert=alert,
            detail=detail,
        )
    finally:
        if conn is not None:
            conn.close()
        sock.close()


async def _handshake_fresh(
    info: tuple[Any, ...],
    sni: str,
    alpn: Sequence[str],
    groups: Sequence[_core.NamedGroup],
    timeout: float,
) -> Attempt:
    """Open a new TCP connection to ``info`` and handshake over it."""
    start = time.perf_counter()
    try:
        sock = await _connect(info, timeout)
    except (OSError, asyncio.TimeoutError) as exc:
        return Attempt(
            offered=tuple(_NAMES[g] for g in groups),
            outcome=Outcome.FAILED,
            elapsed_ms=_elapsed_ms(start),
            detail=f"connect: {_reason(exc)}",
        )
    return await _handshake(sock, sni, alpn, groups, timeout)


# Alerts a server sends when it has no key-exchange group in common with the
# hello, and the wider set that also covers a server without TLS 1.3. Any other
# alert (unrecognized_name, illegal_parameter, internal_error, ...) says
# something else is wrong, so it must not read as "this group is unsupported".
_NO_SHARED_GROUP = frozenset({"handshake_failure", "insufficient_security"})
_NO_TLS13 = _NO_SHARED_GROUP | {"protocol_version"}


def _verdict(attempts: Sequence[Attempt]) -> Verdict:
    pq, *classical = attempts
    if pq.outcome is Outcome.ACCEPTED:
        return Verdict.POST_QUANTUM
    if any(a.outcome is Outcome.ACCEPTED for a in classical):
        if pq.outcome is Outcome.REJECTED and pq.alert in _NO_SHARED_GROUP:
            return Verdict.CLASSICAL_ONLY
        return Verdict.PQ_BLOCKED
    if all(a.outcome is Outcome.REJECTED and a.alert in _NO_TLS13 for a in attempts):
        return Verdict.NO_TLS13
    return Verdict.ERROR


def _explain_error(attempts: Sequence[Attempt]) -> str:
    """Why no handshake worked, for the verdict ``error``."""
    alerts = {a.alert for a in attempts if a.alert}
    if "unrecognized_name" in alerts:
        return "server rejected the server name (unrecognized_name); try --sni"
    seen = [text for a in attempts if (text := a.detail or a.alert)]
    return seen[0] if seen else "no handshake completed"


async def probe(
    host: str,
    port: int = 443,
    *,
    timeout: float = 5.0,
    sni: str | None = None,
    alpn: Sequence[str] = PROBE_ALPN,
) -> ProbeResult:
    """Probe ``host:port`` for post-quantum and classical key-exchange support.

    ``timeout`` bounds each TCP connect and each handshake separately. ``sni``
    overrides the server name sent (default: ``host``; none at all for an IP
    literal, which RFC 6066 forbids, so the answer is the default virtual host's).
    All probes go to the first address that accepts a TCP connection; the result
    records which one.

    Raises :class:`NoPostQuantumSupport` when this build of fizzpy has no
    post-quantum support, since the probe could not tell you anything about ML-KEM.
    """
    if not supports_post_quantum():
        raise NoPostQuantumSupport(
            "this build of fizzpy has no post-quantum support; "
            "install a wheel or build against a liboqs-enabled Fizz"
        )
    loop = asyncio.get_running_loop()

    def unreachable(error: str) -> ProbeResult:
        return ProbeResult(host, port, Verdict.UNREACHABLE, error=error)

    try:
        server_name = sni or _server_name(host)
    except UnicodeError:
        return unreachable("dns: invalid hostname")

    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout
        )
    except (OSError, ValueError, asyncio.TimeoutError) as exc:
        return unreachable(f"dns: {_reason(exc)}")

    last_error = "no addresses"
    for info in infos:
        start = time.perf_counter()
        try:
            first = await _connect(info, timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            last_error = f"connect: {_reason(exc)}"
            continue
        tcp_ms = _elapsed_ms(start)
        address = str(info[4][0])
        break
    else:
        return unreachable(last_error)

    # The connection already open serves the stock-client handshake; every
    # single-group probe takes its own.
    try:
        default, *attempts = _settled(
            await asyncio.gather(
                _handshake(first, server_name, alpn, _DEFAULT_OFFER, timeout),
                *(
                    _handshake_fresh(info, server_name, alpn, (g,), timeout)
                    for g in _PROBE_GROUPS
                ),
                return_exceptions=True,
            )
        )
    finally:
        first.close()  # also covers cancellation before the first handshake ran

    verdict = _verdict(attempts)
    if verdict is Verdict.PQ_BLOCKED:
        # One dropped packet looks the same as a hostile middlebox; only call it
        # blocked if a second try fails too. The stock handshake is redone as
        # well so the result never contradicts its own verdict.
        default, attempts[0] = _settled(
            await asyncio.gather(
                _handshake_fresh(info, server_name, alpn, _DEFAULT_OFFER, timeout),
                _handshake_fresh(info, server_name, alpn, (PQ_GROUP,), timeout),
                return_exceptions=True,
            )
        )
        verdict = _verdict(attempts)

    return ProbeResult(
        host=host,
        port=port,
        verdict=verdict,
        address=address,
        tcp_ms=tcp_ms,
        error=_explain_error(attempts) if verdict is Verdict.ERROR else None,
        attempts=tuple(attempts),
        default=default,
    )


def _settled(results: Sequence[Any]) -> list[Attempt]:
    """Raise the first failure from a ``gather(return_exceptions=True)``.

    Waiting for every sibling first means none is left running, and each has
    already closed its own socket, when the error propagates.
    """
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return list(results)


async def probe_many(
    targets: Iterable[str | tuple[str, int]],
    *,
    concurrency: int = 16,
    timeout: float = 5.0,
    sni: str | None = None,
    alpn: Sequence[str] = PROBE_ALPN,
) -> AsyncIterator[ProbeResult]:
    """Probe many targets, yielding each result as it completes.

    ``targets`` are strings accepted by :func:`parse_target`, or ``(host, port)``
    pairs; strings are all parsed up front so a typo fails before any connection
    is made. ``concurrency``
    bounds hosts in flight (each runs several handshakes at once). ``sni``, if
    given, is sent for every target. Results arrive in completion order, not
    input order.
    """
    parsed = [parse_target(t) if isinstance(t, str) else t for t in targets]
    gate = asyncio.Semaphore(concurrency)

    async def one(host: str, port: int) -> ProbeResult:
        async with gate:
            try:
                return await probe(host, port, timeout=timeout, sni=sni, alpn=alpn)
            except NoPostQuantumSupport:
                raise
            except Exception as exc:  # one bad host must not end a scan
                error = f"{type(exc).__name__}: {exc}"
                return ProbeResult(host, port, Verdict.ERROR, error=error)

    tasks = [asyncio.ensure_future(one(h, p)) for h, p in parsed]
    try:
        for pending in asyncio.as_completed(tasks):
            yield await pending
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
