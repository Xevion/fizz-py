# fizzpy

Post-quantum TLS 1.3 for Python. Keep the HTTP client you already use and swap only
the TLS: fizzpy performs the handshake with the hybrid `X25519MLKEM768` key exchange,
built on Facebook's [Fizz](https://github.com/facebookincubator/fizz) (C++).

**Why.** The key exchange is the part of TLS exposed to "harvest now, decrypt later"
recording, which is why browsers moved to hybrid ML-KEM. In Python, ML-KEM arrived with
OpenSSL 3.5, so an interpreter linked against anything older cannot negotiate it.
fizzpy carries its own TLS stack (Fizz and liboqs), so it works there, and it can
check whether the servers you run or depend on support post-quantum key exchange.
Beta: the API may change before 1.0.

```python
import requests
from fizzpy.contrib.requests import FizzAdapter

session = requests.Session()
session.mount("https://", FizzAdapter())
print(session.get("https://www.cloudflare.com").status_code)
```

requests still owns cookies, redirects, retries and pooling; fizzpy only does the
handshake. The same works under [httpx](docs/requests-httpx.md#httpx), on any
[connected socket](docs/tls.md#any-socket-wrap_socket), or through the small
[built-in client](docs/client.md).

![A fizzpy ClientHello in Wireshark](https://raw.githubusercontent.com/Xevion/fizz-py/master/docs/pq-handshake.png)

*A fizzpy ClientHello in Wireshark: it offers `X25519MLKEM768` (`0x11ec`) plus a
custom marker extension from [`examples/pq_marker.py`](examples/pq_marker.py).*

## Check a server

```console
$ fizzpy probe www.cloudflare.com github.com
HOST                VERDICT         PREFERRED       ML-KEM  x25519  P-256  P-384
www.cloudflare.com  post-quantum    X25519MLKEM768  ok      ok      ok     ok
github.com          classical-only  x25519          rej     ok      ok     rej
```

One handshake per key-exchange group tells "supports ML-KEM" apart from "prefers
x25519", and finds hosts where the larger post-quantum hello gets a connection reset.
It scales to thousands of hosts and prints JSON. See [the probe guide](docs/probe.md).

## Install

```sh
pip install fizzpy
```

Wheels are self-contained (Fizz and liboqs are built in) for Linux x86_64, macOS and
Windows x64, CPython 3.10 to 3.15 including free-threaded builds. For anything else,
see [BUILDING.md](BUILDING.md).

## Limits

- TLS 1.3 only, so TLS 1.2-only servers fail unless you opt into
  [a classical fallback](docs/tls.md#reaching-tls-12-only-hosts).
- HTTP/1.1 only.
- No client certificates yet.

More in [docs/limitations.md](docs/limitations.md).

## Docs

- [Under requests and httpx](docs/requests-httpx.md)
- [Handshake control](docs/tls.md): `wrap_socket`, `TlsConfig`, key exchange,
  extensions, certificates
- [The built-in client](docs/client.md)
- [The probe](docs/probe.md)
- [Building](BUILDING.md)

MIT licensed.
