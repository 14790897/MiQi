"""Runtime event recorder — bridges event creation, seq assignment, and persistence.

Aligns with KUN ``services/runtime-event-recorder.ts``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from miqi.kun_runtime.event_bus import EventBus


class RuntimeEventRecorder:
    """Records runtime events with auto-assigned seq and timestamp.

    In Phase 2 the recorder only writes to the in-memory ``EventBus``.
    Session-store persistence will be wired in Phase 3 via the optional
    ``session_store`` parameter.
    """

    def __init__(
        self,
        event_bus: EventBus,
        now_iso: Callable[[], str] | None = None,
    ):
        self._event_bus = event_bus
        self._now_iso = now_iso or _utc_now_iso

    async def record(self, event: dict[str, Any]) -> dict[str, Any]:
        """Assign seq + timestamp, store on the event bus, and return the enriched event.

        *event* must contain at least ``kind`` and ``threadId``.
        """
        thread_id = str(event.get("threadId", ""))
        if not thread_id:
            raise ValueError("event must have a non-empty threadId")

        seq = self._event_bus.allocate_seq(thread_id)
        enriched: dict[str, object] = {
            **event,
            "seq": seq,
            "timestamp": self._now_iso(),
        }
        self._event_bus.append(thread_id, enriched)
        return enriched  # type: ignore[return-value]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
