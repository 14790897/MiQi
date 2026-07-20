"""Task runner — dispatches incoming submissions to the right handler.

Routes UserMessage through TurnRunner, handles AbortTurn, and emits
typed protocol events onto the shared event queue.
"""

from __future__ import annotations

import uuid
import asyncio
import inspect
from typing import Any

from loguru import logger

from miqi.protocol.commands import (
    AbortTurn,
    ApprovalResponse,
    CompactCommand,
    ConfigUpdate,
    RunUserShellCommand,
    SteerTurn,
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
        # Phase 41: active turn tracking
        self._active_turn_ids: dict[str, str] = {}
        self._turn_steer_queues: dict[str, asyncio.Queue] = {}
        # Lazily initialised SessionManager for dual-write compatibility
        self._legacy_sm: Any = None

    async def _save_to_session_manager(self, *, role: str, content: str, **extra: Any) -> None:
        """Dual-write a message to the legacy SessionManager JSONL store.

        AppServer-managed sessions use HistoryRuntime (SQLite), but the
        sessions.get handler reads from SessionManager (JSONL).  This mirror
        write keeps both stores in sync so sidebar switching works.

        Extra keyword arguments (e.g. tool_calls, name, tool_call_id) are
        forwarded to ``add_message`` so the frontend can reconstruct file
        operations from stored messages when tracked_files.json is empty.
        """
        try:
            session_id: str = self.services.session_id
            # session_id format: "{client_id}:{session_key}"
            if ":" not in session_id:
                return  # Unknown format — skip
            client_id, session_key = session_id.split(":", 1)
            workspace = getattr(self.services, "workspace", None)
            if workspace is None:
                return
            from miqi.session.manager import SessionManager
            if self._legacy_sm is None:
                self._legacy_sm = SessionManager(workspace)
            # Pass client_id so the session gets owner_client_id in metadata.
            # The sessions_get_handler calls get_or_create with client_id and
            # raises REQUIRES_CLAIM for unowned sessions.
            session = self._legacy_sm.get_or_create(session_key, client_id=client_id)
            session.add_message(role, content, **extra)
            self._legacy_sm.save(session)
        except Exception:
            logger.warning("Failed to mirror message to legacy SessionManager", exc_info=True)

    # ── Phase 41: active turn and steering ────────────────────────────────

    def active_turn_id(self, thread_id: str) -> str | None:
        return self._active_turn_ids.get(thread_id)

    async def steer_turn(
        self,
        *,
        thread_id: str,
        expected_turn_id: str,
        content: str,
        input_items: list[dict[str, Any]],
        client_user_message_id: str | None,
    ) -> bool:
        active = self._active_turn_ids.get(thread_id)
        if active != expected_turn_id:
            return False
        queue = self._turn_steer_queues.get(expected_turn_id)
        if queue is None:
            return False
        await queue.put({
            "content": content,
            "input_items": input_items,
            "client_user_message_id": client_user_message_id,
        })
        return True

    # ── dispatch ──────────────────────────────────────────────────────────

    async def handle(self, submission: Any) -> None:
        """Route a submission to the correct handler."""
        if isinstance(submission, UserMessage):
            await self._handle_user_message(submission)
            return
        if isinstance(submission, SteerTurn):
            accepted = await self.steer_turn(
                thread_id=submission.thread_id,
                expected_turn_id=submission.expected_turn_id,
                content=submission.content,
                input_items=submission.input_items,
                client_user_message_id=submission.client_user_message_id,
            )
            if not accepted:
                await self._events.put(CommandRejectedEvent(
                    command_type="SteerTurn",
                    reason="Active turn not steerable",
                    recoverable=False,
                ))
            return
        if isinstance(submission, AbortTurn):
            # Phase 14 follow-up: signal cancellation to the active turn
            thread_id = getattr(submission, "thread_id", None) or "default"
            cancel_evt = self._turn_cancel_events.get(thread_id)
            if cancel_evt is not None:
                cancel_evt.set()

            # Phase 31.4: cancel any pending approvals for this thread
            # so waiting tool calls are unblocked and no orphan approvals
            # remain in the pending set.
            orchestrator = getattr(self.services, "orchestrator", None)
            cancel_fn = getattr(orchestrator, "cancel_approvals_for_thread", None)
            if callable(cancel_fn) and inspect.iscoroutinefunction(cancel_fn):
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
                    model=getattr(self.services.model_settings, "model", "default"),
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
        if isinstance(submission, RunUserShellCommand):
            await self._handle_user_shell_command(submission)
            return
        if isinstance(submission, UserInputAnswer):
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

    async def _handle_user_shell_command(self, cmd: RunUserShellCommand) -> None:
        command = (cmd.command or "").strip()
        thread_id = cmd.thread_id
        turn_id = cmd.turn_id

        if not command:
            await self._events.put(CommandRejectedEvent(
                command_type="RunUserShellCommand",
                reason="command is required",
                recoverable=False,
            ))
            return

        if not thread_id or not turn_id:
            await self._events.put(CommandRejectedEvent(
                command_type="RunUserShellCommand",
                reason="thread_id and turn_id are required",
                recoverable=False,
            ))
            return

        from types import SimpleNamespace
        from miqi.runtime.agent_registry import AgentRegistry
        from miqi.runtime.permission_profile import PermissionProfile
        from miqi.runtime.turn_context import TurnContext

        metadata = AgentRegistry().resolve("main")
        session_id = getattr(self.services, "session_id", "")
        client_id = session_id.split(":")[0] if ":" in session_id else ""
        turn = TurnContext(
            turn_id=turn_id,
            agent_metadata=metadata,
            thread_id=thread_id,
            workspace=self.services.workspace,
            model=self.services.model_settings.model,
            provider=self.services.provider,
            temperature=self.services.model_settings.temperature,
            max_tokens=self.services.model_settings.max_tokens,
            client_id=client_id,
            session_id=session_id,
        )
        turn.permission_profile = PermissionProfile(workspace=self.services.workspace)

        # Phase 42 fix: connect to thread cancel event so AbortTurn can cancel exec
        cancel_evt = self._turn_cancel_events.get(thread_id)
        if cancel_evt is not None:
            turn.cancel_event = cancel_evt

        ledger = getattr(self.services, "ledger_runtime", None)

        try:
            if cmd.standalone:
                self._active_turn_ids[thread_id] = turn_id
                # Ledger: record turn start
                if ledger is not None:
                    await ledger.append_item(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        item_type="turn_started",
                        payload={"agent_name": metadata.name, "source": "userShell"},
                    )
                await self._events.put(TurnStartedEvent(
                    turn_id=turn_id,
                    agent_name=metadata.name,
                    thread_id=thread_id,
                ))

            call = SimpleNamespace(
                id=f"user-shell-{turn_id}",
                name="exec",
                arguments={
                    "command": command,
                    **({"working_dir": cmd.cwd} if cmd.cwd else {}),
                    "_exec_source": "userShell",
                },
            )
            tool_runtime = getattr(self.services, "tool_runtime", None)
            if tool_runtime is None:
                err_msg = "Runtime has no tool runtime"
                if cmd.standalone:
                    if ledger is not None:
                        await ledger.append_item(
                            thread_id=thread_id,
                            turn_id=turn_id,
                            item_type="error",
                            payload={"recoverable": False, "source": "task_runner"},
                        )
                    await self._events.put(TurnCompleteEvent(
                        turn_id=turn_id,
                        thread_id=thread_id,
                        outcome="error",
                        tools_used=[],
                        token_usage={},
                    ))
                else:
                    await self._events.put(CommandRejectedEvent(
                        command_type="RunUserShellCommand",
                        reason=err_msg,
                        recoverable=False,
                    ))
                return

            ctx = await tool_runtime.execute_one(turn, call)
            if cmd.standalone:
                from miqi.execution.orchestrator import OrchestrationResult
                outcome = (
                    "success"
                    if ctx.status == OrchestrationResult.SUCCESS
                    else "error"
                )
                if ledger is not None:
                    await ledger.append_item(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        item_type="turn_completed",
                        payload={"outcome": outcome, "tools_used": ["exec"]},
                    )
                await self._events.put(TurnCompleteEvent(
                    turn_id=turn_id,
                    thread_id=thread_id,
                    outcome=outcome,
                    tools_used=["exec"],
                    token_usage={},
                ))
        except asyncio.CancelledError:
            if cmd.standalone and ledger is not None:
                await ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="turn_aborted",
                    payload={"reason": "Shell command was cancelled."},
                )
            raise
        except Exception:
            logger.exception("User shell command failed for turn {}", turn_id)
            if cmd.standalone:
                if ledger is not None:
                    await ledger.append_item(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        item_type="error",
                        payload={"recoverable": False, "source": "task_runner"},
                    )
                await self._events.put(TurnCompleteEvent(
                    turn_id=turn_id,
                    thread_id=thread_id,
                    outcome="error",
                    tools_used=["exec"],
                    token_usage={},
                ))
            await self._events.put(ErrorEvent(
                turn_id=turn_id,
                severity=EventSeverity.ERROR,
                message="An internal error occurred while running the shell command.",
                recoverable=False,
            ))
        finally:
            if cmd.standalone:
                self._active_turn_ids.pop(thread_id, None)

    async def _handle_user_message(self, msg: UserMessage) -> None:
        turn_id = msg.turn_id or str(uuid.uuid4())[:12]
        thread_id = msg.thread_id or "cli:default"

        # Phase 14 follow-up: register a cancel event so AbortTurn can
        # signal this specific turn to stop. Reuse existing event if a
        # previous turn on the same thread hasn't been cleaned up yet.
        cancel_evt = self._turn_cancel_events.get(thread_id)
        if cancel_evt is None:
            cancel_evt = asyncio.Event()
            self._turn_cancel_events[thread_id] = cancel_evt

        # Phase 41: register steer queue and active turn id
        steer_queue: asyncio.Queue = asyncio.Queue()
        self._active_turn_ids[thread_id] = turn_id
        self._turn_steer_queues[turn_id] = steer_queue

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
            model=self.services.model_settings.model,
            provider=self.services.provider,
            execution_policy=msg.mode or "edit",
            temperature=self.services.model_settings.temperature,
            max_tokens=self.services.model_settings.max_tokens,
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

        # ── Execution Policy ──────────────────────────────────────────
        # Three-layer: system prompt + tool set + approval flags.
        # Mode = Agent role, not permission preset.
        # Plan:   strategist — read-only, proposes approach
        # Manual: collaborator — all tools, each step confirmed by user
        # Edit:   developer  — all tools, safe auto, dangerous ask
        # Auto:   agent      — all tools, bypass approval entirely

        _EP_WRITE_EXEC_TOOLS = frozenset({
            "write_file", "edit_file", "apply_patch", "edit_diff",
            "write", "edit", "delete", "move",
            "exec", "bash", "shell",
            "spawn", "subagent", "cron",
            "skill_manage", "memory",
        })

        if turn.execution_policy == "plan":
            tools = [t for t in tools if t.get("name") not in _EP_WRITE_EXEC_TOOLS]

        if turn.execution_policy == "auto":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.force_approval = True
        # edit: both flags False → normal approval flow
        # plan: read-only tools, approval not reached

        _MODE_PROMPTS = {
            "plan": (
                "【Agent 模式：规划】你的角色是规划师。只分析、制定方案，不执行。"
                "请给出具体的、可操作的方案（包含工具名、文件路径、步骤）。"
                "方案末尾注明：切换到「允许编辑」或「自动」模式即可执行。\n\n"
            ),
            "manual": (
                "【Agent 模式：手动】你的角色是协作者。你有全部工具，但每个操作需要用户确认。"
                "请逐步说明你打算做什么（改哪个文件、执行什么命令），等待用户逐一批准后再动手。\n\n"
            ),
            "edit": (
                "【Agent 模式：允许编辑】你的角色是工程师。直接修改文件，安全操作自动放行。"
                "危险操作（执行命令、网络请求、删除文件）需要用户确认。高效工作。\n\n"
            ),
            "auto": (
                "【Agent 模式：自动】你的角色是全权代理。完全自主执行，不中断询问。"
                "直接完成任务，注意安全底线。用户信任你的判断。\n\n"
            ),
        }
        mode_prompt = _MODE_PROMPTS.get(turn.execution_policy, "")
        effective_system_prompt = mode_prompt + metadata.system_prompt if mode_prompt else metadata.system_prompt

        # ── End Execution Policy ─────────────────────────────────────

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
            auto_limit = getattr(self.services.model_settings, "context_limit_chars", 0)
            if history_runtime is not None and ctx_runtime is not None and auto_limit:
                token_limit = max(1, int(int(auto_limit) / 2.5))
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
            payload_fields: dict[str, Any] = {}
            if msg.input_items:
                payload_fields["input_items"] = msg.input_items
            if msg.client_user_message_id:
                payload_fields["client_user_message_id"] = msg.client_user_message_id
            if history_runtime is not None:
                await history_runtime.append_message(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    role="user",
                    content=msg.content,
                    payload={"message_fields": payload_fields},
                )
            # Dual-write to legacy SessionManager JSONL so sessions.get
            # (which reads JSONL) finds messages created via AppServer flow.
            await self._save_to_session_manager(
                role="user", content=msg.content)
            # Phase 24: record user message in ledger
            if ledger is not None:
                await ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="message",
                    role="user",
                    content=msg.content,
                    payload={"message_fields": payload_fields},
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
                system_prompt=effective_system_prompt,
                tools=tools,
                history=history,
                cancel_event=cancel_evt,
                steer_queue=steer_queue,
            )

            # Persist assistant messages to all stores in a single pass.
            # Build the extra-fields mapping once per message so every
            # persistence destination receives the same metadata.
            for message in result.messages_delta:
                role = message["role"]
                content = message.get("content") or ""
                extra_fields = {k: v for k, v in message.items() if k not in ("role", "content")}

                if history_runtime is not None:
                    await history_runtime.append_message(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        role=role,
                        content=content,
                        payload={"message_fields": extra_fields},
                    )

                # Dual-write to legacy SessionManager (independent of history_runtime
                # so fallback JSONL is always populated). Forward all extra fields
                # (tool_calls, name, tool_call_id, etc.) so get_history() preserves
                # them and the frontend can reconstruct file operations.
                await self._save_to_session_manager(
                    role=role, content=content, **extra_fields,
                )

                if ledger is not None:
                    await ledger.append_item(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        item_type="message",
                        role=role,
                        content=content,
                        payload={"message_fields": extra_fields},
                    )

            if history_runtime is not None:
                await history_runtime.complete_turn(
                    turn_id,
                    status="completed",
                    tools_used=result.tools_used,
                    token_usage=result.token_usage,
                )
            # Phase 24: complete turn in ledger
            if ledger is not None:
                await ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="turn_completed",
                    payload={
                        "final_content": result.final_content,
                        "token_usage": result.token_usage,
                    },
                )

            tool_calls: list[dict[str, Any]] = []
            for message in result.messages_delta:
                if message.get("role") == "assistant":
                    tool_calls.extend(message.get("tool_calls") or [])

            await self._events.put(AgentMessageEvent(
                turn_id=turn_id,
                content=result.final_content or "",
                finish_reason="stop",
                tool_calls=tool_calls,
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
            # Phase 57: a ProviderError carries a classified error_kind from
            # the provider (rate_limit/auth/context_length/...). Surface the
            # category + recoverability and, for user-actionable kinds, the
            # provider's own message. Non-ProviderError exceptions keep the
            # original generic internal-error behavior.
            from miqi.providers.resilience import ErrorKind, ProviderError
            prov_err = exc if isinstance(exc, ProviderError) else None
            error_kind = prov_err.kind.value if prov_err is not None else None
            recoverable = prov_err.recoverable if prov_err is not None else False
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
                    payload={
                        "recoverable": recoverable,
                        "source": "task_runner",
                        "error_kind": error_kind,
                    },
                )
            # Log full details server-side, send sanitized message to client.
            # User-actionable kinds (rate_limit/auth/context_length/
            # invalid_request) are safe + actionable, so surface the provider
            # message; everything else (transient/fatal/unknown) keeps the
            # generic message to avoid leaking internal details.
            logger.error("Agent processing error in turn {}: {}", turn_id, exc, exc_info=True)
            user_message = "An internal error occurred while processing your message."
            if prov_err is not None and prov_err.kind is ErrorKind.AUTH:
                # AUTH is sensitive — surface a fixed, non-leaking message
                # instead of the raw provider exception text (Plan 58.2).
                user_message = "模型服务认证失败，请检查 Provider 的 API Key、API Base 或当前模型配置。"
            elif prov_err is not None and prov_err.kind in (
                ErrorKind.RATE_LIMIT,
                ErrorKind.CONTEXT_LENGTH,
                ErrorKind.INVALID_REQUEST,
            ):
                user_message = prov_err.message or user_message
            await self._events.put(ErrorEvent(
                turn_id=turn_id,
                severity=EventSeverity.ERROR,
                message=user_message,
                recoverable=recoverable,
                error_kind=error_kind,
            ))
            await self._events.put(TurnCompleteEvent(
                turn_id=turn_id,
                thread_id=thread_id,
                outcome="error",
                tools_used=[],
                token_usage={},
            ))
        finally:
            # Only clear entries this turn still owns — a concurrent turn
            # on the same thread may have reused the cancel event and
            # overwritten the active turn id (PR #58 fix).
            if self._turn_cancel_events.get(thread_id) is cancel_evt:
                self._turn_cancel_events.pop(thread_id, None)
            if self._active_turn_ids.get(thread_id) == turn_id:
                self._active_turn_ids.pop(thread_id, None)
            self._turn_steer_queues.pop(turn_id, None)

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
