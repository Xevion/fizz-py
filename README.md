# fizzpy

A small TLS 1.3 HTTP client for Python, built on Facebook's
[Fizz](https://github.com/facebookincubator/fizz) (C++) via pybind11.

By default it offers a **post-quantum key exchange** — the standardized hybrid
`X25519MLKEM768` group (codepoint 4588). An ordinary `GET` negotiates a hybrid
ML-KEM handshake against servers that support it (Cloudflare, Google) and falls
back to classical X25519 against those that don't.

> TLS 1.3 only, HTTP/1.1 only. This is a focused toolkit / learning project,
> not a drop-in `requests` replacement. See [Status](#status).

## Usage

Synchronous:

```python
import fizzpy

r = fizzpy.get("https://www.cloudflare.com")
print(r.status_code)               # 200
print(r.headers["content-type"])   # text/html; charset=UTF-8
print(r.text[:64])

# The negotiated TLS 1.3 parameters are attached to every response:
print(r.tls)
# {'version': 'TLSv1.3', 'cipher': 'TLS_AES_128_GCM_SHA256',
#  'group': 'X25519MLKEM768', 'group_code': 4588,
#  'alpn': 'http/1.1', 'sni': 'www.cloudflare.com', 'peer_cert': '...'}
```

Asynchronous (the same C++ core, resolved on the running event loop):

```python
import asyncio
from fizzpy.aio import AsyncClient

async def main():
    async with AsyncClient() as client:
        r = await client.get("https://www.google.com")
        print(r.status_code, r.tls["group"], r.tls["group_code"])

asyncio.run(main())
```

### Choosing the key exchange

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

### Certificate verification

Certificate chains are verified against the system trust store and the
hostname is checked against the certificate's SAN by default. Point at a custom
CA, or disable verification entirely:

```python
fizzpy.Client(cafile="/path/to/ca.pem")   # trust a specific CA
fizzpy.Client(verify=False)               # accept any certificate (insecure)
```

## Status

What works today:

- TLS 1.3 handshake with classical or post-quantum (ML-KEM) key exchange
- `GET`/`POST`/`HEAD`/`PUT`/`DELETE`, sync and async
- HTTP/1.1 response framing (content-length, chunked, gzip/deflate)
- Chain + hostname certificate verification, custom CA trust

Current limitations:

- **TLS 1.3 only** (a Fizz constraint) — it cannot talk to TLS 1.2-only servers
- HTTP/1.1 only (no HTTP/2)
- One connection per request — no keep-alive yet
- No automatic redirect following yet

## Building

There are no prebuilt wheels yet; the post-quantum handshake requires a Fizz
built against [liboqs](https://github.com/open-quantum-safe/liboqs). See
[BUILDING.md](BUILDING.md) for the from-source recipe.
