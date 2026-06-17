"""Adapters that plug fizzpy's Fizz TLS layer into existing HTTP clients.

Each submodule targets one client and is imported on demand, so importing
``fizzpy`` never requires the client to be installed:

- :mod:`fizzpy.contrib.requests` — a ``requests``/urllib3 transport adapter.
- :mod:`fizzpy.contrib.httpx` — an ``httpx`` transport.
"""
