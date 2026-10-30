# Under requests and httpx

fizzpy sits below your HTTP client: the client keeps its cookies, redirects,
retries and pooling, and fizzpy performs the TLS handshake. The negotiated
parameters live on the `TlsSocket` (`.tls`); with `requests` that is
`r.raw.connection.sock.tls`, which only exists while the connection is still
attached, so use `stream=True` as below. It is an implementation detail of the
client libraries, not a stable API.

## requests / urllib3

`FizzAdapter` is a standard `requests` transport adapter (install the extra:
`pip install fizzpy[requests]`). Mount it and every HTTPS request the session
makes handshakes through Fizz, and everything above TLS (cookies, redirects,
retries, pooling, proxies) is still plain requests.

```python
import requests
from fizzpy.contrib.requests import FizzAdapter

session = requests.Session()
session.mount("https://", FizzAdapter())

r = session.get("https://www.cloudflare.com")
print(r.status_code)   # 200

# stream=True keeps urllib3's connection attached so the TlsSocket is reachable:
with session.get("https://www.cloudflare.com", stream=True) as r:
    print(r.raw.connection.sock.tls["group_code"])  # 4588
```

Shape the handshake with a [`TlsConfig`](tls.md#tlsconfig); the usual `HTTPAdapter`
keyword arguments (`max_retries`, `pool_connections`, and so on) still work:

```python
from fizzpy import TlsConfig, NamedGroup
from fizzpy.contrib.requests import FizzAdapter

pq_only = TlsConfig(groups=[NamedGroup.x25519_mlkem768])
session.mount("https://", FizzAdapter(pq_only, max_retries=3))
```

Verification follows requests' own `verify=` argument: `verify="/path/ca.pem"`
trusts a specific CA, `verify=False` disables it. Hostname checking happens
inside the Fizz handshake.

## httpx

`FizzHTTPTransport` is an `httpx` transport (install the extra:
`pip install fizzpy[httpx]`). Hand it to `httpx.Client(transport=...)` and httpx
keeps cookies, redirects, pooling, and its request/response models while Fizz
does the handshake.

```python
import httpx
from fizzpy import TlsConfig, NamedGroup
from fizzpy.contrib.httpx import FizzHTTPTransport

client = httpx.Client(transport=FizzHTTPTransport())

r = client.get("https://www.cloudflare.com")
print(r.status_code)   # 200

# The negotiated handshake is on the TlsSocket; stream to keep it reachable:
with client.stream("GET", "https://www.cloudflare.com") as r:
    sock = r.extensions["network_stream"].get_extra_info("socket")
    print(sock.tls["group_code"])  # 4588

# Shape the handshake with a TlsConfig:
client = httpx.Client(transport=FizzHTTPTransport(
    TlsConfig(groups=[NamedGroup.x25519_mlkem768])
))
```

Unlike the requests adapter, TLS is configured via `TlsConfig`, **not** httpx's
`verify=`. httpx has no separate `ssl_context` parameter, so fizzpy must occupy
the `verify=` slot to install itself, so httpx's own `verify=`/`cert=`
can't also be honored. `FizzHTTPTransport` rejects them (and `http2=True`, which
it can't support) with a clear error rather than silently ignoring them.

## Behaviour

- **Errors.** TLS failures raise the client's native SSL error:
  `requests.exceptions.SSLError`, `httpx.ConnectError`, or
  `ssl.SSLCertVerificationError` / `ssl.SSLError` from `wrap_socket`. Messages carry
  no C++ internals, so existing `except` blocks keep working.
- **Timeouts.** `settimeout` and the `timeout=` of requests/httpx bound each read and
  write, so a stalled peer raises `socket.timeout` (`ReadTimeout`) instead of hanging.
- **Threads.** Every connection runs on one shared event loop, so a mounted
  `FizzAdapter` is safe to use from many threads at once.
- **Proxies.** A plain `CONNECT` proxy works with no extra setup: the client opens the
  tunnel and fizzpy handshakes over it. An HTTPS proxy (TLS to the proxy itself) is not
  supported; fizzpy would attempt a post-quantum handshake against the proxy.
- **TLS 1.2-only hosts.** See [the opt-in fallback](tls.md#reaching-tls-12-only-hosts).
