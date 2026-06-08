"""Lightweight cancellation token for KUN runtime.

Aligns with KUN ``TurnService.inflightTurns`` abort controller plus
``InflightTracker``.

Uses ``asyncio.Event`` as the signal; callers poll ``is_set()`` or
``await wait()`` instead of relying on JS-style AbortSignal listeners.
"""

from __future__ import annotations

import asyncio
from typing import Any


class CancellationToken:
    """A simple cooperative cancellation token.

    Usage::

        token = CancellationToken()
        ...
        if token.is_set():
            return  # abort early
        ...
        token.cancel()
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()

    @property
    def cancelled(self) -> bool:
        """Alias for ``is_set()`` matching JS convention."""
        return self._event.is_set()


class InflightTracker:
    """Track running operations (model calls, tool executions) per thread/turn.

    Aligns with KUN ``loop/inflight-tracker.ts``.
    """

    def __init__(self) -> None:
        self._inflight: dict[str, dict[str, Any]] = {}

    def begin(self, op: dict[str, Any]) -> None:
        """Register an inflight operation. *op* must have ``id``."""
        op_id = str(op.get("id", ""))
        if not op_id:
            raise ValueError("inflight operation requires an id")
        self._inflight[op_id] = op

    def end(self, op_id: str) -> None:
        self._inflight.pop(op_id, None)

    def count(self, thread_id: str | None = None) -> int:
        """Return count of inflight ops, optionally filtered by thread."""
        if thread_id is None:
            return len(self._inflight)
        return sum(
            1 for op in self._inflight.values()
            if op.get("threadId") == thread_id
        )

    def is_running(self, op_id: str) -> bool:
        return op_id in self._inflight
