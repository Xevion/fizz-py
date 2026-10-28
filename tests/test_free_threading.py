"""Free-threaded (no-GIL) CPython support.

``_core`` declares itself GIL-free, so importing it must not flip the
interpreter back to GIL-enabled. A single sync ``Client`` shared by many threads
also exercises the pooled-connection hand-off with genuine parallelism, which
the GIL otherwise masks.
"""

import sys
import sysconfig
import threading

import pytest

import fizzpy

free_threaded = pytest.mark.skipif(
    not sysconfig.get_config_var("Py_GIL_DISABLED"),
    reason="needs a free-threaded CPython build",
)

THREADS = 16
REQUESTS_PER_THREAD = 8


@free_threaded
def test_importing_core_keeps_the_gil_disabled():
    assert not sys._is_gil_enabled()  # pyright: ignore[reportPrivateUsage]


def test_shared_client_across_threads(local_server):
    errors: list[BaseException] = []
    start = threading.Barrier(THREADS)

    with fizzpy.Client(verify=False, timeout=10) as client:

        def worker() -> None:
            try:
                start.wait(timeout=10)
                for _ in range(REQUESTS_PER_THREAD):
                    r = client.get(local_server.url)
                    assert r.status_code == 200
                    assert r.text == "hello from local tls"
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not any(t.is_alive() for t in threads), "a worker thread hung"
    assert not errors, errors[:3]
