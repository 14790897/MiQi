"""Safe async helpers for mixing sync and async code.

The bridge dispatches handlers synchronously (from stdin line-read loop),
but some handlers need to call async APIs (e.g. PluginManager.discover).
These helpers provide a safe way to run coroutines from sync contexts
without triggering "coroutine was never awaited" warnings.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_async_safely(coro: Coroutine[Any, Any, T], *, timeout: float | None = 30.0) -> T:
    """Run a coroutine and return its result, regardless of the current loop state.

    - No running loop → uses asyncio.run().
    - Running loop already → dispatches to a one-shot thread so the
      coroutine runs in its own fresh loop without nesting.

    Args:
        coro: The coroutine to run.
        timeout: Seconds to wait for the result (only used in thread path).
               None means wait forever.

    Returns:
        The coroutine's return value.

    Raises:
        concurrent.futures.TimeoutError: If timeout is exceeded in the
            thread path (not the asyncio.run path).
        Exception: Any exception raised by the coroutine propagates.
    """
    try:
        asyncio.get_running_loop()  # Check — raises RuntimeError if no loop running
    except RuntimeError:
        # No event loop is running — safe to use asyncio.run()
        return asyncio.run(coro)

    # An event loop is already running.  Create a fresh loop in a
    # background thread so we don't nest run_until_complete inside
    # a running loop.
    # NOTE: This is a stopgap for sync bridge handlers.  When those
    # handlers are migrated to async (Phase 13+), this path should
    # become unnecessary.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=timeout)
