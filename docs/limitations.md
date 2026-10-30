# Limitations

- **TLS 1.3 only.** This is a Fizz constraint. By default a request to a TLS
  1.2-only server fails loudly; opt into a stdlib `ssl` fallback with
  `fallback=True` to reach it over a classical handshake instead (see
  [the fallback](tls.md#reaching-tls-12-only-hosts)).
- **HTTP/1.1 only.** No HTTP/2.
- **Adapters.** requests/urllib3 and httpx (sync) are packaged. An async httpx
  transport and an aiohttp connector could be built on the same primitive but are not
  shipped.
- **Client certificates (mutual TLS)** are not supported, and CA trust is a single
  bundle file (no `capath`/`cadata`).
- **HTTPS proxies** (TLS to the proxy itself) are not supported. Plain `CONNECT`
  proxies work.
- **Platforms.** Wheels cover Linux x86_64, macOS (arm64, x86_64) and Windows x64.
  There are no Linux aarch64 wheels yet.
