"""Task runner — dispatches incoming submissions to the right handler.

Routes UserMessage through AgentLoop, handles AbortTurn, and emits
typed protocol events onto the shared event queue.
"""

from __future__ import annotations

import uuid
import asyncio
from typing import Any

from miqi.protocol.commands import (
    AbortTurn,
    ApprovalResponse,
    ConfigUpdate,
    ThreadCommand,
    UserMessage,
)
from miqi.protocol.events import AgentMessageEvent, ErrorEvent, EventSeverity


class TaskRunner:
    """Dispatches submissions and converts AgentLoop output to typed events.

    Does NOT own services — it receives them from RuntimeSession.
    """

    def __init__(self, *, services: Any, event_queue: Any):
        self.services = services
        self._events = event_queue

    async def handle(self, submission: Any) -> None:
        """Route a submission to the correct handler."""
        if isinstance(submission, UserMessage):
            await self._handle_user_message(submission)
            return
        if isinstance(submission, AbortTurn):
            self.services.agent_loop.stop()
            return
        if isinstance(submission, (ApprovalResponse, ConfigUpdate, ThreadCommand)):
            await self._events.put(ErrorEvent(
                turn_id=str(uuid.uuid4())[:12],
                severity=EventSeverity.WARNING,
                message=f"Submission type {type(submission).__name__} is not wired in Phase 11",
                recoverable=True,
            ))
            return
        await self._events.put(ErrorEvent(
            turn_id=str(uuid.uuid4())[:12],
            severity=EventSeverity.ERROR,
            message=f"Unknown submission type: {type(submission).__name__}",
            recoverable=False,
        ))

    async def _handle_user_message(self, msg: UserMessage) -> None:
        turn_id = str(uuid.uuid4())[:12]
        try:
            thread_id = msg.thread_id or "cli:default"
            result = await self.services.agent_loop.process_direct(
                msg.content,
                session_key=thread_id,
                channel=getattr(msg, "channel", None) or "runtime",
                chat_id=thread_id,
            )
            await self._events.put(AgentMessageEvent(
                turn_id=turn_id,
                content=result or "",
                finish_reason="stop",
            ))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._events.put(ErrorEvent(
                turn_id=turn_id,
                severity=EventSeverity.ERROR,
                message=str(exc),
                recoverable=False,
            ))
