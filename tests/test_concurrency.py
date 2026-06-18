"""Concurrent use of pooled Fizz connections across threads.

The whole core runs on one shared EventBase thread, and every operation is
serialised onto it via ``runInEventBaseThread``; each connection owns its own
state. So many Python threads driving separate pooled connections at once must
neither corrupt state nor deadlock. This stress-tests that guarantee.
"""

import threading

import pytest

import fizzpy

requests = pytest.importorskip("requests")
from fizzpy.contrib.requests import FizzAdapter  # noqa: E402

THREADS = 24
REQUESTS_PER_THREAD = 5


def test_concurrent_pool_requests(local_server):
    session = requests.Session()
    session.mount(
        "https://",
        FizzAdapter(
            fizzpy.TlsConfig(verify=False),
            pool_connections=16,
            pool_maxsize=16,
        ),
    )
    errors: list[BaseException] = []
    # Release every worker at once so the handshakes/reads genuinely overlap on
    # the single EventBase thread, rather than trickling through serially.
    start = threading.Barrier(THREADS)

    def worker() -> None:
        try:
            start.wait(timeout=10)
            for _ in range(REQUESTS_PER_THREAD):
                # A bounded read timeout turns any genuine stall into a fast
                # failure (recorded below) instead of wedging the whole suite.
                r = session.get(local_server.url, verify=False, timeout=10)
                assert r.status_code == 200
                assert r.text == "hello from local tls"
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "a worker thread hung"
    assert not errors, errors[:3]
