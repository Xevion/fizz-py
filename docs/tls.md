# Handshake control

Everything that shapes the TLS handshake: the socket primitive, `TlsConfig`, the key
exchange, custom ClientHello extensions, certificate trust, and the opt-in TLS 1.2
fallback.

## Any socket: `wrap_socket`

The adapters are built on a single primitive: hand fizzpy an already-connected
socket and get back a blocking, `ssl.SSLSocket`-shaped object. This is how you
plug Fizz under anything that lets you supply your own TLS:

```python
import socket, fizzpy

tcp = socket.create_connection(("www.cloudflare.com", 443))
tls = fizzpy.wrap_socket(tcp, "www.cloudflare.com")

tls.sendall(b"GET / HTTP/1.1\r\nHost: www.cloudflare.com\r\n"
            b"Connection: close\r\n\r\n")
print(tls.tls["group"])   # X25519MLKEM768
print(tls.recv(64))
```

The socket's file descriptor is duplicated and handed to Fizz's event loop, so
the caller keeps full control of the original `tcp` socket (close it whenever;
the TLS connection lives on through the dup). The returned `TlsSocket` supports
`recv`/`recv_into`, `send`/`sendall`, `makefile`, `settimeout`, `fileno`, and
`close`, which is the slice of the socket API `http.client`/urllib3 drive.

## TlsConfig

`TlsConfig` is the frozen set of handshake knobs shared by `wrap_socket` and the
contrib adapters:

```python
from fizzpy import TlsConfig, NamedGroup, Extension

config = TlsConfig(
    verify=True,                              # chain + hostname verification
    cafile="/path/to/ca.pem",                 # default: certifi bundle
    alpn=["http/1.1"],
    groups=[NamedGroup.x25519_mlkem768, NamedGroup.x25519],
    extensions=[Extension(0xFE5A, b"hi")],    # custom ClientHello extensions
    timeout=30.0,
)
```

## Choosing the key exchange

The default offers `[x25519_mlkem768, x25519]`, mirroring how Chrome and Firefox
send both key shares. Override it per client:

```python
import fizzpy
from fizzpy import NamedGroup

# Force post-quantum only (handshake fails if the server lacks ML-KEM):
pq = fizzpy.Client(groups=[NamedGroup.x25519_mlkem768])

# Classical only:
classical = fizzpy.Client(groups=[NamedGroup.x25519])
```

## Custom ClientHello extensions

fizzpy surfaces Fizz's low-level extension hook, so you can append arbitrary
extensions to the TLS 1.3 ClientHello. Each is an opaque `(type, data)` pair;
fizzpy rejects types it manages itself (key_share, supported_versions, and so on) and
out-of-range or duplicate types.

```python
import fizzpy

client = fizzpy.Client(
    extensions=[fizzpy.Extension(0xFE5A, b"hello from fizzpy")],
)
r = client.get("https://blog.cloudflare.com")
print(r.tls["group"])   # still negotiates X25519MLKEM768
```

The extension is sent verbatim in the ClientHello. See it on the wire with
[`examples/pq_marker.py`](../examples/pq_marker.py) and the Wireshark screenshot in
the README.

## Certificate verification

Certificate chains are verified against the [certifi](https://github.com/certifi/python-certifi)
CA bundle and the hostname is checked against the certificate's SAN by default.
Point at a custom CA, or disable verification entirely:

```python
fizzpy.Client(cafile="/path/to/ca.pem")   # trust a specific CA
fizzpy.Client(verify=False)               # accept any certificate (insecure)
```

## Reaching TLS 1.2-only hosts

Fizz speaks TLS 1.3 only, so by default a request to a TLS 1.2-only server fails
loudly: a post-quantum handshake is the whole point, and silently downgrading would
defeat it. When you'd rather reach such hosts anyway, opt into a fallback. On a
version-mismatch failure, fizzpy retries the connection over the standard library
`ssl` module, which gives a classical (non post-quantum) handshake.

```python
session.mount("https://", FizzAdapter(fallback=True))           # requests
httpx.Client(transport=FizzHTTPTransport(fallback=True))        # httpx
```

The fallback fires **only** on a `protocol_version` alert. A certificate or
hostname failure still raises: a bad cert is never downgraded into a successful
classical handshake. The retry honours the same `TlsConfig` verification (CA
bundle, `verify=False`) the Fizz handshake would have used.
