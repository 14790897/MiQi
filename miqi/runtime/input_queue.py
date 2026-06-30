"""Prioritized input queue for agent message processing."""

from __future__ import annotations

import asyncio
import heapq
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class _PrioritizedItem:
    priority: int
    seq: int
    item: Any = field(compare=False)


class InputQueue:
    """A priority queue for agent inputs.

    Lower priority numbers are processed first.
    Default priorities:
      0 — abort/control commands
      1 — approval responses
      10 — user messages
    """

    def __init__(self):
        self._queue: list[_PrioritizedItem] = []
        self._counter: int = 0
        self._event = asyncio.Event()

    async def push(self, item: Any, priority: int = 10) -> None:
        heapq.heappush(
            self._queue,
            _PrioritizedItem(priority=priority, seq=self._counter, item=item),
        )
        self._counter += 1
        self._event.set()

    async def pop(self, timeout: float | None = 1.0) -> Any | None:
        if self._queue:
            entry = heapq.heappop(self._queue)
            self._event.clear()
            return entry.item

        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

        if self._queue:
            entry = heapq.heappop(self._queue)
            self._event.clear()
            return entry.item
        return None

    async def clear(self) -> None:
        self._queue.clear()
        self._event.clear()

    def __len__(self) -> int:
        return len(self._queue)
