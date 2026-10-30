# Probing a server for post-quantum support

A normal handshake only shows what the server *chose*, and a server that prefers
x25519 looks the same as one that cannot do ML-KEM at all. `fizzpy probe` offers one
key-exchange group per connection and records the server's answer.

```console
$ fizzpy probe www.cloudflare.com github.com 127.0.0.1:8443
HOST                VERDICT         PREFERRED       ML-KEM  x25519  P-256  P-384
www.cloudflare.com  post-quantum    X25519MLKEM768  ok      ok      ok     ok
github.com          classical-only  x25519          rej     ok      ok     rej
127.0.0.1:8443      unreachable     -               -       -       -      -      connect: connection refused
```

Each cell is one handshake: `ok` completed, `rej` the server answered with a TLS alert,
`FAIL` the connection broke without one (reset, close, timeout). `PREFERRED` is what a
stock client ends up with when it offers ML-KEM then x25519, so a host can be
`post-quantum` (it supports ML-KEM) and still prefer x25519.

## Verdicts

| Verdict | Meaning |
| --- | --- |
| `post-quantum` | completes a handshake with X25519MLKEM768 |
| `classical-only` | TLS 1.3 works; the server answers the ML-KEM group with "no common group" |
| `pq-blocked` | classical handshakes work, but the post-quantum hello breaks the handshake |
| `no-tls13` | every offer drew a "no TLS 1.3 / no common group" alert |
| `unreachable` | no TCP connection (DNS, refused, timeout) |
| `error` | connected, but no handshake worked for another reason; the `error` field says why |

`pq-blocked` is the failure that breaks clients as ML-KEM rolls out, and a normal
request never shows it because the host works classically. The ML-KEM key share makes
the ClientHello about 1.2 KB larger, which some middleboxes and old TLS stacks mishandle
when it spans packets. The probe cannot tell a server bug, a middlebox and the network
path apart, nor distinguish a size problem from a problem with the ML-KEM codepoint. A
suspected block is retried once before it is reported.

Only `handshake_failure` and `insufficient_security` count as "no common group". Any
other alert (`unrecognized_name`, `illegal_parameter`, `internal_error`, ...) means
something else is wrong, so it never reads as `classical-only`.

## Command line

```sh
fizzpy probe -f hosts.txt              # one target per line, '#' comments allowed
fizzpy probe -v example.com            # every handshake: timings, alerts, cipher, cert
fizzpy probe --json -f hosts.txt       # one JSON object per host, as each finishes
fizzpy probe --require-pq example.com  # exit 1 unless every target is post-quantum
```

Targets are `host`, `host:port`, `[v6]:port` or an `https://` URL. `-c` sets how many
hosts are probed at once (default 16, each uses several sockets) and `-t` the timeout
for each connect and handshake in seconds. Exit status is 0 on success, 1 when
`--require-pq` fails, and 2 for usage errors or a build without post-quantum support.

## What the probe does not measure

- **Certificates are not validated.** This measures key-exchange support, not trust.
- **One address per host.** All probes go to the first address that accepts a TCP
  connection, and the result records which. A round-robin or anycast host may answer
  differently elsewhere, and a CDN or proxy answers for itself, not its origin.
- **IP targets send no server name** (RFC 6066 forbids one), so the answer is the
  default virtual host's. `--sni NAME` sets a name for every target.
- **Four groups.** X25519MLKEM768, x25519, secp256r1 and secp384r1: the groups Fizz can
  run a key exchange for. Pure ML-KEM and P-256/P-384 hybrids are not probed.
- **No HelloRetryRequest test.** Every probe sends a key share for the group it offers,
  so a server that would retry into ML-KEM from a classical-only share is not exercised.
- **Size effects are best effort.** Whether a large hello is split across packets
  depends on the path, so a size-related bug can be missed.

## Library

```python
import asyncio
from fizzpy.probe import probe, probe_many

result = asyncio.run(probe("www.cloudflare.com"))
print(result.verdict, result.accepted_groups, result.preferred)

async def scan(hosts):
    async for r in probe_many(hosts, concurrency=64):   # results as they complete
        print(r.host, r.verdict.value)
```

`probe_many` isolates failures: an unexpected error on one host becomes an `error`
result instead of ending the scan. `ProbeResult.to_dict()` is what `--json` prints.
`fizzpy.supports_post_quantum()` says whether the installed build can do ML-KEM at all
(always true for the wheels; false for a source build against a Fizz without liboqs,
where the probe refuses to run).
