"""In-memory per-thread event bus with monotonically increasing seq numbers.

Aligns with KUN ``adapters/in-memory-event-bus.ts``.
Events are stored per-thread in append order. Subscribers can replay
history from a `sinceSeq` offset and receive new events via async iterator.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator


class EventBus:
    """Thread-scoped, pub/sub event bus.

    Each thread has its own sequence counter and event log.  Subscribers
    receive events through an ``AsyncIterator`` so the SSE layer can
    continuously push new events to connected clients.
    """

    def __init__(self) -> None:
        # threadId → list of events (all fields as dicts for wire compat)
        self._events: dict[str, list[dict[str, object]]] = {}
        # threadId → next seq (monotonic, starts at 1)
        self._next_seq: dict[str, int] = {}
        # threadId → list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, object]]]] = {}

    # ── seq management ──────────────────────────────────────────────────

    def allocate_seq(self, thread_id: str) -> int:
        """Reserve and return the next seq for *thread_id*.

        Callers can use the returned seq before emitting via ``append``
        if they need to reorder or pre-assign.
        """
        seq = self._next_seq.get(thread_id, 0) + 1
        self._next_seq[thread_id] = seq
        if thread_id not in self._events:
            self._events[thread_id] = []
        return seq

    # ── event storage ───────────────────────────────────────────────────

    def append(self, thread_id: str, event: dict[str, object]) -> None:
        """Store an event.  *event* must already contain ``seq`` and ``timestamp``."""
        if thread_id not in self._events:
            self._events[thread_id] = []
        self._events[thread_id].append(event)
        self._notify_subscribers(thread_id, event)

    # ── history replay ──────────────────────────────────────────────────

    def history(self, thread_id: str, since_seq: int = 0) -> list[dict[str, object]]:
        """Return events for *thread_id* whose seq > *since_seq*."""
        events = self._events.get(thread_id, [])
        if since_seq <= 0:
            return list(events)
        return [e for e in events if isinstance(e.get("seq"), int) and int(e["seq"]) > since_seq]  # type: ignore[arg-type]

    def count(self, thread_id: str) -> int:
        """Return the total number of stored events for *thread_id*."""
        return len(self._events.get(thread_id, []))

    # ── subscriptions ───────────────────────────────────────────────────

    async def subscribe(self, thread_id: str, since_seq: int = 0) -> AsyncIterator[dict[str, object]]:
        """Yield past events from *since_seq*, then live events as they arrive.

        Usage::

            async for event in bus.subscribe("th1", since_seq=5):
                yield format_sse(event)
        """
        que: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

        # Register
        if thread_id not in self._subscribers:
            self._subscribers[thread_id] = []
        self._subscribers[thread_id].append(que)  # type: ignore[arg-type]

        try:
            # Replay history
            for event in self.history(thread_id, since_seq):
                yield event

            # Live events
            while True:
                event = await que.get()
                if event is None:  # sentinel: unsubscribe
                    break
                yield event
        finally:
            subs = self._subscribers.get(thread_id)
            if subs and que in subs:
                subs.remove(que)  # type: ignore[arg-type]

    def _notify_subscribers(self, thread_id: str, event: dict[str, object]) -> None:
        """Push *event* to all subscriber queues for *thread_id*."""
        for que in self._subscribers.get(thread_id, []):
            try:
                que.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer — drop event (SSE client will re-sync via since_seq)

    def unsubscribe_all(self, thread_id: str) -> None:
        """Send sentinel to all subscribers for *thread_id* and clear them."""
        for que in self._subscribers.pop(thread_id, []):
            try:
                que.put_nowait(None)
            except asyncio.QueueFull:
                pass
