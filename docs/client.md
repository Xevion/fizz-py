# The built-in client

fizzpy also ships a small standalone client, handy for scripts and for seeing
the negotiated parameters directly. It drives the same C++ core.

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

Asynchronous (the same core, resolved on the running event loop):

```python
import asyncio
from fizzpy.aio import AsyncClient

async def main():
    async with AsyncClient() as client:
        r = await client.get("https://www.google.com")
        print(r.status_code, r.tls["group"], r.tls["group_code"])

asyncio.run(main())
```

Keep-alive connections are pooled per host, redirects are followed, and responses
are framed for content-length, chunked and gzip/deflate bodies. Key exchange,
extensions and certificate trust are configured as in [handshake control](tls.md).
