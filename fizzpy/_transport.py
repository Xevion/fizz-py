"""Bridges between the C++ core's resolve/reject callbacks and Python.

Every async operation on :class:`fizzpy._core.TlsConnection` is submitted with a
``(resolve, reject)`` pair that the core invokes — while holding the GIL — from
its background EventBase thread once the operation completes. These helpers turn
that single callback contract into either a blocking call (sync facade) or an
awaitable (asyncio facade), so both facades share one core.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

Submit = Callable[[Callable[[Any], None], Callable[[BaseException], None]], None]


def run_sync(submit: Submit) -> Any:
    """Submit an op and block the calling thread until it resolves.

    The wait happens on a :class:`threading.Event`, so the GIL is released while
    blocked and the core's EventBase thread is free to drive the connection.
    """
    done = threading.Event()
    box: dict[str, Any] = {}

    def resolve(result: Any) -> None:
        box["result"] = result
        done.set()

    def reject(error: BaseException) -> None:
        box["error"] = error
        done.set()

    submit(resolve, reject)
    done.wait()
    if "error" in box:
        raise box["error"]
    return box["result"]


async def run_async(submit: Submit) -> Any:
    """Submit an op and await it on the running asyncio loop.

    The core resolves from its own thread, so completion is marshalled back onto
    the loop with ``call_soon_threadsafe``.
    """
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[Any] = loop.create_future()

    def resolve(result: Any) -> None:
        loop.call_soon_threadsafe(_set_result, fut, result)

    def reject(error: BaseException) -> None:
        loop.call_soon_threadsafe(_set_exception, fut, error)

    submit(resolve, reject)
    return await fut


def _set_result(fut: asyncio.Future, result: Any) -> None:
    if not fut.done():
        fut.set_result(result)


def _set_exception(fut: asyncio.Future, error: BaseException) -> None:
    if not fut.done():
        fut.set_exception(error)
