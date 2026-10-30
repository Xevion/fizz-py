#!/usr/bin/env python3
"""cibuildwheel `test-command`: the installed wheel must still do post-quantum TLS.

A Fizz bump that drops liboqs would build fine and ship a wheel that silently
negotiates classical groups only, so every wheel asserts the hybrid key exchange
is available. It then attempts a real handshake against a peer that hangs up: a
working build fails it with an SSL error, while a platform that cannot duplicate
and adopt the socket handle fails earlier with a plain OSError.
"""

import socket
import ssl
import threading

import fizzpy

assert fizzpy.supports_post_quantum(), "wheel was built without post-quantum support"

listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(1)


def hang_up() -> None:
    peer, _ = listener.accept()
    peer.recv(65536)
    peer.close()


threading.Thread(target=hang_up, daemon=True).start()
client = socket.create_connection(listener.getsockname(), timeout=10)
try:
    fizzpy.wrap_socket(client, "localhost", fizzpy.TlsConfig(verify=False, timeout=10))
except ssl.SSLError:
    pass
else:
    raise SystemExit("handshake against a peer that hung up unexpectedly succeeded")
finally:
    client.close()
    listener.close()

print("post-quantum key exchange available; socket adoption works")
