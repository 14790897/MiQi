"""Task runner — dispatches incoming submissions to the right handler.

Routes UserMessage through TurnRunner, handles AbortTurn, and emits
typed protocol events onto the shared event queue.
"""

from __future__ import annotations

import uuid
import asyncio
from typing import Any

from miqi.protocol.commands import (
    AbortTurn,
    ApprovalResponse,
    CompactCommand,
    ConfigUpdate,
    RunUserShellCommand,
    ThreadCommand,
    UserInputAnswer,
    UserMessage,
)
from miqi.protocol.events import (
    AgentMessageEvent,
    ApprovalResolvedEvent,
    CommandRejectedEvent,
    ConfigUpdatedEvent,
    ContextCompactedEvent,
    ErrorEvent,
    EventSeverity,
    TurnAbortedEvent,
    TurnCompleteEvent,
    TurnStartedEvent,
)


class TaskRunner:
    """Dispatches submissions and converts TurnRunner output to typed events.

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

            # Phase 31.4: cancel any pending approvals for this thread
            # so waiting tool calls are unblocked and no orphan approvals
            # remain in the pending set.
            orchestrator = getattr(self.services, "orchestrator", None)
            cancel_fn = getattr(orchestrator, "cancel_approvals_for_thread", None)
            if callable(cancel_fn) and asyncio.iscoroutinefunction(cancel_fn):
                await cancel_fn(thread_id, reason="Turn aborted by user.")

            await self._events.put(ErrorEvent(
                turn_id=str(uuid.uuid4())[:12],
                severity=EventSeverity.WARNING,
                message=f"Turn aborted for thread {thread_id}.",
                recoverable=True,
            ))
            return
        if isinstance(submission, ApprovalResponse):
            # Phase 18: resolve orchestrator approval
            orchestrator = getattr(self.services, "orchestrator", None)
            if orchestrator is None or not hasattr(orchestrator, "resolve_approval"):
                await self._events.put(CommandRejectedEvent(
                    command_type="ApprovalResponse",
                    reason="Runtime has no approval resolver",
                    recoverable=False,
                ))
                return
            result = orchestrator.resolve_approval(
                submission.approval_id,
                submission.decision,
            )
            # Phase 31.4: only emit terminal ApprovalResolvedEvent when
            # the orchestrator confirms the approval was actually resolved.
            # Invalid/nonexistent approvals emit CommandRejectedEvent instead.
            if result.resolved:
                await self._events.put(ApprovalResolvedEvent(
                    approval_id=result.approval_id,
                    decision=result.normalized_decision,
                    turn_id=result.turn_id,
                ))
            else:
                await self._events.put(CommandRejectedEvent(
                    command_type="ApprovalResponse",
                    reason=result.reason or "Approval resolution failed",
                    recoverable=False,
                ))
            return
        if isinstance(submission, ThreadCommand):
            await self._handle_thread_command(submission)
            return
        if isinstance(submission, ConfigUpdate):
            # Phase 18: mutate session state and emit ConfigUpdatedEvent.
            # All failure paths must emit CommandRejectedEvent, never crash.
            state = getattr(self.services, "session_state", None)
            if state is None or not hasattr(state, "apply_config_update"):
                await self._events.put(CommandRejectedEvent(
                    command_type="ConfigUpdate",
                    reason="Runtime has no mutable session state",
                    recoverable=False,
                ))
                return
            try:
                state.apply_config_update(submission.path, submission.value)
            except (ValueError, AttributeError, TypeError) as exc:
                await self._events.put(CommandRejectedEvent(
                    command_type="ConfigUpdate",
                    reason=str(exc),
                    recoverable=False,
                ))
                return
            await self._events.put(ConfigUpdatedEvent(
                path=submission.path,
                value=submission.value,
            ))
            return
        if isinstance(submission, CompactCommand):
            # Phase 19: trigger context compaction via ContextRuntime
            ctx_runtime = getattr(self.services, "context_runtime", None)
            history_runtime = getattr(self.services, "history_runtime", None)
            if ctx_runtime is None or history_runtime is None:
                await self._events.put(CommandRejectedEvent(
                    command_type="CompactCommand",
                    reason="Runtime has no context or history manager",
                    recoverable=False,
                ))
                return
            compact_turn_id = f"compact-{str(uuid.uuid4())[:12]}"
            try:
                result = await ctx_runtime.compact_thread(
                    history_runtime=history_runtime,
                    thread_id=submission.thread_id,
                    turn_id=compact_turn_id,
                    model=getattr(self.services.agent_loop, "model", "default"),
                )
            except Exception as exc:
                await self._events.put(CommandRejectedEvent(
                    command_type="CompactCommand",
                    reason=str(exc),
                    recoverable=True,
                ))
                return
            await self._events.put(ContextCompactedEvent(
                turn_id=compact_turn_id,
                thread_id=result.thread_id,
                messages_before=result.messages_before,
                messages_after=result.messages_after,
                tokens_saved=result.tokens_saved,
            ))
            return
        if isinstance(submission, (UserInputAnswer, RunUserShellCommand)):
            await self._events.put(CommandRejectedEvent(
                command_type=type(submission).__name__,
                reason=f"{type(submission).__name__} is reserved for future use",
                recoverable=True,
            ))
            return
        await self._events.put(CommandRejectedEvent(
            command_type=type(submission).__name__,
            reason=f"Unknown submission type: {type(submission).__name__}",
            recoverable=False,
        ))

    async def _handle_user_message(self, msg: UserMessage) -> None:
        turn_id = str(uuid.uuid4())[:12]
        thread_id = msg.thread_id or "cli:default"

        # Phase 14 follow-up: register a cancel event so AbortTurn can
        # signal this specific turn to stop.
        cancel_evt = asyncio.Event()
        self._turn_cancel_events[thread_id] = cancel_evt

        # Phase 17: get history runtime for persistence and loading
        history_runtime = getattr(self.services, "history_runtime", None)
        # Phase 24: get ledger runtime for append-only event recording
        ledger = getattr(self.services, "ledger_runtime", None)

        # Build TurnContext and run through TurnRunner (Phase 12)
        from miqi.runtime.agent_registry import AgentRegistry
        from miqi.runtime.turn_context import TurnContext

        metadata = AgentRegistry().resolve("main")
        # Phase 31.4: extract client_id from session_id (format: client_id:session_key).
        # This is a best-effort derivation; a dedicated client_id field on
        # RuntimeServices would be a future improvement.
        session_id = getattr(self.services, "session_id", "")
        client_id = session_id.split(":")[0] if ":" in session_id else ""
        turn = TurnContext(
            turn_id=turn_id,
            agent_metadata=metadata,
            thread_id=thread_id,
            workspace=self.services.workspace,
            model=self.services.agent_loop.model,
            provider=self.services.provider,
            temperature=self.services.agent_loop.temperature,
            max_tokens=self.services.agent_loop.max_tokens,
            client_id=client_id,
            session_id=session_id,
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

        try:
            # Phase 17: load history and start turn tracking
            if history_runtime is not None:
                await history_runtime.start_turn(turn_id, thread_id=thread_id)
                history = await history_runtime.load_messages(thread_id)
            else:
                history = []

            # Phase 24: record turn start in ledger
            if ledger is not None:
                await ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="turn_started",
                    payload={"agent_name": metadata.name},
                )

            # Phase 19: auto-compact before turn if history exceeds budget
            ctx_runtime = getattr(self.services, "context_runtime", None)
            auto_limit = getattr(self.services.agent_loop, "context_limit_chars", 0)
            if history_runtime is not None and ctx_runtime is not None and auto_limit:
                token_limit = max(1, int(auto_limit) // 4)
                if ctx_runtime.should_auto_compact(history, token_limit):
                    try:
                        compact_result = await ctx_runtime.compact_thread(
                            history_runtime=history_runtime,
                            thread_id=thread_id,
                            turn_id=f"compact-{turn_id}",
                            model=turn.model,
                        )
                        await self._events.put(ContextCompactedEvent(
                            turn_id=turn_id,
                            thread_id=thread_id,
                            messages_before=compact_result.messages_before,
                            messages_after=compact_result.messages_after,
                            tokens_saved=compact_result.tokens_saved,
                        ))
                        # Reload compacted history for the turn
                        history = await history_runtime.load_messages(thread_id)
                    except Exception as compact_exc:
                        # Compaction failed — log and emit recoverable
                        # ErrorEvent, then proceed with unbounded history.
                        from loguru import logger
                        logger.exception(
                            "Auto-compact failed for thread {}: {}",
                            thread_id, compact_exc,
                        )
                        await self._events.put(ErrorEvent(
                            turn_id=turn_id,
                            severity=EventSeverity.WARNING,
                            message=(
                                f"Context compaction failed for thread "
                                f"{thread_id}: {compact_exc}"
                            ),
                            recoverable=True,
                        ))

            # Emit TurnStartedEvent
            await self._events.put(TurnStartedEvent(
                turn_id=turn_id,
                agent_name=metadata.name,
                thread_id=thread_id,
            ))

            # Persist the user message
            if history_runtime is not None:
                await history_runtime.append_message(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    role="user",
                    content=msg.content,
                )
            # Phase 24: record user message in ledger
            if ledger is not None:
                await ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="message",
                    role="user",
                    content=msg.content,
                    payload={"message_fields": {}},
                )

            # Check for abort before starting turn
            if cancel_evt.is_set():
                if history_runtime is not None:
                    await history_runtime.complete_turn(
                        turn_id,
                        status="aborted",
                        tools_used=[],
                        token_usage={},
                    )
                if ledger is not None:
                    await ledger.append_item(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        item_type="turn_aborted",
                        payload={"reason": "Turn aborted before start."},
                    )
                await self._events.put(TurnAbortedEvent(
                    turn_id=turn_id,
                    thread_id=thread_id,
                    reason="Turn aborted before start.",
                ))
                return

            result = await self.services.turn_runner.run(
                turn=turn,
                user_content=msg.content,
                system_prompt=metadata.system_prompt,
                tools=tools,
                history=history,
                cancel_event=cancel_evt,
            )

            # Phase 17: persist assistant messages and complete turn
            if history_runtime is not None:
                for message in result.messages_delta:
                    await history_runtime.append_message(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        role=message["role"],
                        content=message.get("content") or "",
                        payload={
                            "message_fields": {
                                k: v for k, v in message.items()
                                if k not in {"role", "content"}
                            },
                        },
                    )
                await history_runtime.complete_turn(
                    turn_id,
                    status="completed",
                    tools_used=result.tools_used,
                    token_usage=result.token_usage,
                )
            # Phase 24: record assistant messages and turn completion in ledger
            if ledger is not None:
                for message in result.messages_delta:
                    await ledger.append_item(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        item_type="message",
                        role=message.get("role"),
                        content=message.get("content") or "",
                        payload={
                            "message_fields": {
                                k: v for k, v in message.items()
                                if k not in {"role", "content"}
                            },
                        },
                    )
                await ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="turn_completed",
                    payload={
                        "final_content": result.final_content,
                        "token_usage": result.token_usage,
                    },
                )

            await self._events.put(AgentMessageEvent(
                turn_id=turn_id,
                content=result.final_content or "",
                finish_reason="stop",
            ))
            await self._events.put(TurnCompleteEvent(
                turn_id=turn_id,
                thread_id=thread_id,
                outcome="success",
                tools_used=result.tools_used,
                token_usage=result.token_usage,
            ))
        except asyncio.CancelledError:
            if history_runtime is not None:
                await history_runtime.complete_turn(
                    turn_id,
                    status="aborted",
                    tools_used=[],
                    token_usage={},
                )
            if ledger is not None:
                await ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="turn_aborted",
                    payload={"reason": "Turn was cancelled."},
                )
            await self._events.put(TurnAbortedEvent(
                turn_id=turn_id,
                thread_id=thread_id,
                reason="Turn was cancelled.",
            ))
            raise
        except Exception as exc:
            if history_runtime is not None:
                await history_runtime.complete_turn(
                    turn_id,
                    status="error",
                    tools_used=[],
                    token_usage={},
                )
            if ledger is not None:
                await ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="error",
                    payload={"recoverable": False, "source": "task_runner"},
                )
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

    async def _handle_thread_command(self, cmd: ThreadCommand) -> None:
        """Phase 18: dispatch thread lifecycle actions to ThreadRuntime.

        All failure paths emit CommandRejectedEvent — no exceptions
        escape to the caller.
        """
        from miqi.protocol.events import (
            ThreadCreatedEvent,
            ThreadDeletedEvent,
            ThreadUpdatedEvent,
        )

        threads = getattr(self.services, "thread_runtime", None)
        if threads is None:
            await self._events.put(CommandRejectedEvent(
                command_type="ThreadCommand",
                reason="Runtime has no thread manager",
                recoverable=False,
            ))
            return

        if cmd.action == "new":
            try:
                thread = await threads.create_thread(
                    title=cmd.params.get("title", "New thread"),
                    thread_id=cmd.params.get("thread_id"),
                )
            except (KeyError, ValueError, AttributeError, TypeError) as exc:
                await self._events.put(CommandRejectedEvent(
                    command_type="ThreadCommand",
                    reason=str(exc),
                    recoverable=False,
                ))
                return
            await self._events.put(ThreadCreatedEvent(
                thread_id=thread.thread_id,
                title=thread.title,
                parent_thread_id=thread.parent_thread_id,
            ))
            return

        if cmd.action == "rename":
            if "title" not in cmd.params or not cmd.params["title"]:
                await self._events.put(CommandRejectedEvent(
                    command_type="ThreadCommand",
                    reason="rename requires a non-empty 'title' in params",
                    recoverable=False,
                ))
                return
            try:
                thread = await threads.rename_thread(cmd.thread_id, cmd.params["title"])
            except (KeyError, ValueError, AttributeError, TypeError) as exc:
                await self._events.put(CommandRejectedEvent(
                    command_type="ThreadCommand",
                    reason=str(exc),
                    recoverable=False,
                ))
                return
            await self._events.put(ThreadUpdatedEvent(
                thread_id=thread.thread_id,
                title=thread.title,
                status=thread.status,
            ))
            return

        if cmd.action == "archive":
            try:
                thread = await threads.archive_thread(cmd.thread_id)
            except (KeyError, ValueError, AttributeError, TypeError) as exc:
                await self._events.put(CommandRejectedEvent(
                    command_type="ThreadCommand",
                    reason=str(exc),
                    recoverable=False,
                ))
                return
            await self._events.put(ThreadUpdatedEvent(
                thread_id=thread.thread_id,
                title=thread.title,
                status=thread.status,
            ))
            return

        if cmd.action == "delete":
            try:
                await threads.delete_thread(cmd.thread_id)
            except (KeyError, ValueError, AttributeError, TypeError) as exc:
                await self._events.put(CommandRejectedEvent(
                    command_type="ThreadCommand",
                    reason=str(exc),
                    recoverable=False,
                ))
                return
            await self._events.put(ThreadDeletedEvent(thread_id=cmd.thread_id))
            return

        if cmd.action == "fork":
            try:
                thread = await threads.fork_thread(
                    cmd.thread_id,
                    title=cmd.params.get("title", "Forked thread"),
                )
            except (KeyError, ValueError, AttributeError, TypeError) as exc:
                await self._events.put(CommandRejectedEvent(
                    command_type="ThreadCommand",
                    reason=str(exc),
                    recoverable=False,
                ))
                return
            await self._events.put(ThreadCreatedEvent(
                thread_id=thread.thread_id,
                title=thread.title,
                parent_thread_id=thread.parent_thread_id,
            ))
            return

        await self._events.put(CommandRejectedEvent(
            command_type="ThreadCommand",
            reason=f"Unknown thread action: {cmd.action}",
            recoverable=False,
        ))
