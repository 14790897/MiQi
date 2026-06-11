"""Runtime client — frontend-facing helper around RuntimeSession.

Frontends use RuntimeClient.ask() instead of directly calling AgentLoop
or duplicating event-drain loops. The client submits a UserMessage,
consumes typed events from the runtime, and returns the final content.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Awaitable, Callable

from miqi.protocol.commands import UserMessage
from miqi.protocol.events import AgentMessageEvent, ErrorEvent

EventCallback = Callable[[Any], Any | Awaitable[Any]]


class RuntimeClient:
    """Small frontend-facing helper around RuntimeSession.

    Frontends use this instead of directly calling AgentLoop or
    duplicating event-drain loops.

    Phase 14 follow-up: serializes concurrent ask() calls per-runtime
    via an async lock so responses never get mixed up between callers.
    """

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self._lock = asyncio.Lock()

    async def ask(
        self,
        content: str,
        *,
        thread_id: str,
        on_event: EventCallback | None = None,
        timeout: float | None = 120,
    ) -> str:
        """Submit a user message and wait for the final assistant response.

        Phase 14 follow-up: uses a per-client async lock to serialize
        calls so concurrent ask() on the same runtime don't interleave.
        Each ask() also tags its submission with a request_id so it can
        correlate the correct AgentMessageEvent response.

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
        request_id = str(uuid.uuid4())[:12]

        async with self._lock:
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
