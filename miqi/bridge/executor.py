"""Persistent background executor for Desktop mode subagent tasks.

Desktop mode creates a temporary asyncio event loop per request (via asyncio.run()).
Subagent tasks need to outlive those requests. This module provides a stable event
loop running in a daemon thread where subagents can execute independently.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine

from loguru import logger


class BackgroundExecutor:
    """
    A persistent event loop running in a daemon thread.

    Usage:
        executor = BackgroundExecutor()
        executor.start()
        future = executor.submit(some_coroutine())
        # future completes independently of the caller's event loop
        executor.stop()
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()

    def start(self) -> None:
        """Start the background event loop thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._started.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="miqi-subagent-executor",
            daemon=True,
        )
        self._thread.start()
        if not self._started.wait(timeout=5.0):
            raise RuntimeError("BackgroundExecutor failed to start within 5s")
        logger.info("BackgroundExecutor started (thread={})", self._thread.name)

    def _run_loop(self) -> None:
        """Thread entry: create and run a new event loop forever."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()
        # Cleanup after stop
        self._loop.close()

    @property
    def is_running(self) -> bool:
        return self._loop is not None and self._loop.is_running()

    def submit(self, coro: Coroutine[Any, Any, Any]) -> asyncio.futures.Future:
        """Submit a coroutine to the persistent loop (thread-safe).

        Returns a concurrent.futures.Future that resolves when the coroutine completes.
        Can be awaited from any thread/loop, or polled with .done()/.result().
        """
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("BackgroundExecutor not running — call start() first")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self) -> None:
        """Stop the background loop and join the thread."""
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("BackgroundExecutor thread did not stop cleanly")
        self._loop = None
        self._thread = None
        logger.info("BackgroundExecutor stopped")
