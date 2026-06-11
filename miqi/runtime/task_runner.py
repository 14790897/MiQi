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
        # Phase 14 follow-up: per-thread active turn cancellation event
        self._turn_cancel_events: dict[str, asyncio.Event] = {}

    async def handle(self, submission: Any) -> None:
        """Route a submission to the correct handler."""
        if isinstance(submission, UserMessage):
            await self._handle_user_message(submission)
            return
        if isinstance(submission, AbortTurn):
            # Phase 14 follow-up: signal cancellation to the active turn
            # instead of calling agent_loop.stop()
            thread_id = getattr(submission, "thread_id", None) or "default"
            cancel_evt = self._turn_cancel_events.get(thread_id)
            if cancel_evt is not None:
                cancel_evt.set()
            await self._events.put(ErrorEvent(
                turn_id=str(uuid.uuid4())[:12],
                severity=EventSeverity.WARNING,
                message=f"Turn aborted for thread {thread_id}.",
                recoverable=True,
            ))
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
        thread_id = msg.thread_id or "cli:default"

        # Phase 14 follow-up: register a cancel event so AbortTurn can
        # signal this specific turn to stop.
        cancel_evt = asyncio.Event()
        self._turn_cancel_events[thread_id] = cancel_evt
        try:
            # Build TurnContext and run through TurnRunner (Phase 12)
            from miqi.runtime.agent_registry import AgentRegistry
            from miqi.runtime.turn_context import TurnContext

            metadata = AgentRegistry().resolve("main")
            turn = TurnContext(
                turn_id=turn_id,
                agent_metadata=metadata,
                thread_id=thread_id,
                workspace=self.services.workspace,
                model=self.services.agent_loop.model,
                provider=self.services.provider,
                temperature=self.services.agent_loop.temperature,
                max_tokens=self.services.agent_loop.max_tokens,
            )

            # Phase 13: resolve capabilities and permission profile
            tools: list[dict[str, Any]] = []
            capability_resolver = getattr(self.services, "capability_resolver", None)
            if capability_resolver is not None:
                capabilities = capability_resolver.resolve(agent_metadata=metadata)
                turn.capabilities = capabilities
                tools = capabilities.tool_definitions
            else:
                tools = self.services.tool_registry.get_definitions()

            # Phase 13: attach permission profile for orchestrator
            from miqi.runtime.permission_profile import PermissionProfile
            turn.permission_profile = PermissionProfile(
                workspace=self.services.workspace,
            )

            # Check for abort before starting turn
            if cancel_evt.is_set():
                await self._events.put(ErrorEvent(
                    turn_id=turn_id,
                    severity=EventSeverity.WARNING,
                    message="Turn aborted before start.",
                    recoverable=True,
                ))
                return

            result = await self.services.turn_runner.run(
                turn=turn,
                user_content=msg.content,
                system_prompt=metadata.system_prompt,
                tools=tools,
                cancel_event=cancel_evt,
            )
            await self._events.put(AgentMessageEvent(
                turn_id=turn_id,
                content=result.final_content or "",
                finish_reason="stop",
            ))
        except asyncio.CancelledError:
            await self._events.put(ErrorEvent(
                turn_id=turn_id,
                severity=EventSeverity.WARNING,
                message="Turn was cancelled.",
                recoverable=True,
            ))
            raise
        except Exception as exc:
            # Log full details server-side, send sanitized message to client
            from loguru import logger
            logger.error("Agent processing error in turn {}: {}", turn_id, exc, exc_info=True)
            await self._events.put(ErrorEvent(
                turn_id=turn_id,
                severity=EventSeverity.ERROR,
                message="An internal error occurred while processing your message.",
                recoverable=False,
            ))
        finally:
            self._turn_cancel_events.pop(thread_id, None)
