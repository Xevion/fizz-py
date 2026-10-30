#!/usr/bin/env python3
"""cibuildwheel `test-command`: the installed wheel must still do post-quantum TLS.

A Fizz bump that drops liboqs would build fine and ship a wheel that silently
negotiates classical groups only, so every wheel asserts the hybrid key exchange
is available before it is accepted.
"""

import fizzpy

assert fizzpy.supports_post_quantum(), "wheel was built without post-quantum support"
print("post-quantum key exchange available")
