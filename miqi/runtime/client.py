"""Runtime client — frontend-facing helper around RuntimeSession.

Historical: Frontends now use RuntimeClient.ask() instead of directly
calling the legacy AgentLoop. The client submits a UserMessage, consumes
typed events from the runtime, and returns the final content.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from miqi.protocol.commands import UserMessage
from miqi.protocol.events import AgentMessageEvent, ErrorEvent

EventCallback = Callable[[Any], Any | Awaitable[Any]]


class RuntimeClient:
    """Small frontend-facing helper around RuntimeSession.

    Historical: Frontends use this instead of directly calling the legacy
    AgentLoop or duplicating event-drain loops.

    Phase 14 follow-up v2: ask() serialization uses the runtime-owned
    _ask_lock (not a per-client lock) so multiple RuntimeClient instances
    sharing the same RuntimeSession don't interleave responses.
    """

    def __init__(self, runtime: Any):
        self.runtime = runtime

    async def ask(
        self,
        content: str,
        *,
        thread_id: str,
        on_event: EventCallback | None = None,
        timeout: float | None = 120,
    ) -> str:
        """Submit a user message and wait for the final assistant response.

        Uses runtime._ask_lock to serialize concurrent ask() calls across
        all RuntimeClient instances that share the same RuntimeSession.
        Each call submits, then drains events until its AgentMessageEvent.

        Args:
            content: The user's message text.
            thread_id: Thread to submit to.
            on_event: Optional callback for progress/status events.
            timeout: Max seconds to wait for a response.

        Returns:
            The assistant's final content string.

        Raises:
            TimeoutError: If no response arrives within timeout.
            RuntimeError: If the runtime emits an ErrorEvent.
        """
        lock = getattr(self.runtime, "_ask_lock", None)
        if lock is not None:
            await lock.acquire()
        try:
            await self.runtime.submit(
                UserMessage(content=content, thread_id=thread_id)
            )

            while True:
                event = await self.runtime.next_event(timeout=timeout)
                if event is None:
                    raise TimeoutError("Timed out waiting for runtime response")

                if isinstance(event, AgentMessageEvent):
                    return event.content

                if isinstance(event, ErrorEvent):
                    raise RuntimeError(event.message)

                if on_event is not None:
                    maybe = on_event(event)
                    if hasattr(maybe, "__await__"):
                        await maybe
        finally:
            if lock is not None and lock.locked():
                lock.release()
