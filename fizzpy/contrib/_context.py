"""A duck-typed ``ssl.SSLContext`` that wraps sockets with Fizz.

Shared by the contrib adapters. Both urllib3 (via ``requests``) and httpcore (via
``httpx``) drive a TLS handshake by calling a small, identical slice of the
``ssl.SSLContext`` API on whatever context they're given — ``set_alpn_protocols``
then ``wrap_socket`` — and neither does an ``isinstance(ctx, ssl.SSLContext)``
check on that path. So one duck-typed context serves both: it performs the
handshake with Fizz instead of OpenSSL and hands back a :class:`TlsSocket`.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import replace
from typing import Any

from fizzpy._tls import TlsConfig, TlsSocket
from fizzpy._tls import wrap_socket as fizz_wrap_socket

__all__ = ["FizzSSLContext"]


class FizzSSLContext:
    """An ``ssl.SSLContext`` look-alike that wraps sockets with Fizz.

    Implements just the surface urllib3 and httpcore drive: it accepts
    ``verify_mode`` / ``check_hostname`` assignments, records the CA file from
    ``load_verify_locations`` and the protocols from ``set_alpn_protocols``, and
    performs the handshake in :meth:`wrap_socket`. ``check_hostname`` defaults to
    ``True`` so the caller trusts fizzpy's in-handshake hostname check and skips
    its own ``getpeercert()`` matching (which a :class:`TlsSocket` does not
    provide).

    ``verify_mode`` is seeded from the :class:`~fizzpy.TlsConfig`, so the context
    reflects the configured trust whether or not the HTTP client overwrites it.
    urllib3 *does* overwrite it (and calls ``load_verify_locations``) from
    ``requests``' per-request ``verify=``; httpcore does not, so for httpx the
    seeded value from the config is what takes effect.

    With ``fallback=True``, a TLS-1.3-incapable peer (which Fizz cannot handshake)
    is reached over the stdlib ``ssl`` module instead — a classical, *non*
    post-quantum handshake. The fallback fires only on a ``protocol_version``
    alert; a certificate or any other handshake failure still raises, so a bad
    cert is never silently downgraded.
    """

    def __init__(
        self, config: TlsConfig | None = None, *, fallback: bool = False
    ) -> None:
        self._config = config or TlsConfig()
        self._cafile = self._config.cafile
        self._alpn: list[str] = list(self._config.alpn)
        self._fallback = fallback
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED if self._config.verify else ssl.CERT_NONE

    def load_verify_locations(
        self,
        cafile: str | None = None,
        capath: str | None = None,
        cadata: str | bytes | None = None,
    ) -> None:
        if capath or cadata:
            raise NotImplementedError(
                "fizzpy trusts a single CA bundle file; capath/cadata are "
                "unsupported. Point the client at a cafile instead."
            )
        if cafile:
            self._cafile = cafile

    def set_alpn_protocols(self, protocols: list[str]) -> None:
        self._alpn = list(protocols)

    def load_cert_chain(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "fizzpy does not support client certificates (mutual TLS) yet"
        )

    def wrap_socket(
        self, sock: Any, server_hostname: str | None = None, **_kwargs: object
    ) -> TlsSocket | ssl.SSLSocket:
        config = replace(
            self._config,
            verify=self.verify_mode != ssl.CERT_NONE,
            cafile=self._cafile,
            alpn=self._alpn,
        )
        if not self._fallback:
            return fizz_wrap_socket(sock, server_hostname or "", config)

        # Capture the peer up front: a failed Fizz handshake resets this TCP
        # connection, so the stdlib retry needs a fresh socket to the same peer.
        peer = sock.getpeername()
        family = sock.family
        try:
            return fizz_wrap_socket(sock, server_hostname or "", config)
        except ssl.SSLError as error:
            if not _is_protocol_version_failure(error):
                raise
            return _stdlib_handshake(sock, peer, family, server_hostname, config)


def _is_protocol_version_failure(error: ssl.SSLError) -> bool:
    """Whether ``error`` is the alert a TLS-1.3-incapable peer sends.

    The only failure the fallback downgrades on. A certificate failure (a
    distinct ``SSLCertVerificationError``) or any other handshake error must
    surface, never trigger an insecure retry.

    The native layer tags handshake errors with the typed Fizz alert via a
    ``fizz_alert`` attribute, so the decision keys on the exact alert
    (``protocol_version``) rather than scraping the message. The substring check
    remains only as a fallback for an error that arrived without the tag.
    """
    if isinstance(error, ssl.SSLCertVerificationError):
        return False
    alert = getattr(error, "fizz_alert", None)
    if alert is not None:
        return alert == "protocol_version"
    return "protocol_version" in str(error)


def _stdlib_handshake(
    dead_sock: Any,
    peer: Any,
    family: int,
    server_hostname: str | None,
    config: TlsConfig,
) -> ssl.SSLSocket:
    """Reconnect to ``peer`` and complete a classical TLS handshake via stdlib.

    Fizz already consumed (and the peer reset) ``dead_sock``, so a new TCP
    connection is opened directly to ``peer``. Verification mirrors the
    :class:`TlsConfig`, but the trust is re-derived from stdlib ``ssl`` (its
    hostname-matching and chain semantics, not Fizz's), and the reconnect goes
    straight to the captured peer — so a connection that reached the origin
    through a proxy ``CONNECT`` tunnel cannot be retried this way.
    """
    dead_sock.close()
    new = socket.socket(family, socket.SOCK_STREAM)
    try:
        new.settimeout(config.timeout)
        new.connect(peer)
        ctx = ssl.create_default_context(cafile=config.resolved_cafile)
        ctx.set_alpn_protocols(list(config.alpn))
        if not config.verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx.wrap_socket(new, server_hostname=server_hostname or None)
    except BaseException:
        new.close()
        raise
