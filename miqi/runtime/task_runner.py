"""Task runner — dispatches incoming submissions to the right handler.

Routes UserMessage through TurnRunner, handles AbortTurn, and emits
typed protocol events onto the shared event queue.
"""

from __future__ import annotations

import dataclasses
import uuid
import asyncio
import inspect
import re
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


def _classify_chain(exc: BaseException):
    """Classify an exception, unwrapping a FATAL wrapper via __cause__/__context__.

    Issue #529: an SDK error that escaped retry (or was re-wrapped by an
    intermediate layer) reaches TaskRunner as a raw exception with no
    ``ProviderError`` tag. ``classify_error`` on the outer wrapper may yield
    ``FATAL`` while the real cause — in ``__cause__``/``__context__`` — still
    carries a meaningful kind (TRANSIENT, RATE_LIMIT, ...). Only when the
    direct classification lands on FATAL do we look one level down the chain;
    a non-FATAL result (or no cause) is returned as-is.
    """
    from miqi.providers.resilience import ErrorKind, classify_error

    kind = classify_error(exc)
    if kind is ErrorKind.FATAL:
        cause = exc.__cause__ or exc.__context__
        if cause is not None and cause is not exc:
            cause_kind = classify_error(cause)
            if cause_kind is not ErrorKind.FATAL:
                return cause_kind
    return kind


def _normalize_skill_ref(text: str) -> str:
    """Normalize a skill reference for matching: lowercase, drop separators.

    'mof-synthesis-price-agent', 'mof synthesis price agent' and
    'mof_synthesis_price_agent' all normalize to 'mofsynthesispriceagent'.
    """
    return re.sub(r"[\s\-_]+", "", text.lower())


def _match_skill_intent(
    user_content: str,
    skills: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Return matched skill records (with 'path') referenced in the message (#613).

    Substring match on normalized names. *skills* is expected in
    SkillsLoader.list_skills order (workspace before builtin), so the
    first hit is the highest-priority match. Empty list when nothing
    matches — the model then falls back to generic tool composition.

    Only identifier-like names participate: names containing a separator
    ('demo-agent', 'mof-synthesis-price-agent') or long single words
    (>= 10 chars). Short common words such as 'weather' or 'pdf' would
    false-positive on everyday language and are left to the LLM's own
    judgment against the injected inventory.

    Returns records (not just names) so callers can load bodies by the
    indexed ``path`` — a nested built-in may have a synthesized display
    name (``plugin-foo``) with no matching directory to load from.
    """
    if not user_content:
        return []
    normalized = _normalize_skill_ref(user_content)
    hits: list[dict[str, str]] = []
    # Match longest names first so a shorter name that is a substring of a
    # longer one (e.g. 'demo-agent' vs 'demo-agent-ex') cannot shadow it.
    for s in sorted(skills, key=lambda r: len(r["name"]), reverse=True):
        name = s["name"]
        if not (
            "-" in name or "_" in name or " " in name or len(name) >= 10
        ):
            continue
        # Reject empty normalized names: a directory named '---' (or any
        # separator-only name) normalizes to '' — '' in normalized is always
        # True, which would preload that skill on every message.
        normalized_name = _normalize_skill_ref(name)
        if normalized_name and normalized_name in normalized:
            hits.append(s)
    return hits


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

        from miqi.runtime.tool_policy import PLAN_BLOCKED_TOOLS

        if turn.execution_policy == "plan":
            tools = [t for t in tools if t.get("name") not in PLAN_BLOCKED_TOOLS]
            # NOTE: Plan mode only exposes read-only tools (write/exec/spawn
            # removed by PLAN_BLOCKED_TOOLS above).  Setting bypass_approval
            # here skips approval prompts for safe read operations — it does
            # NOT grant write/execute permission.  Tool filtering (above) is
            # the security boundary.  The permission engine's deny-list still
            # wins in all modes.
            turn.bypass_approval = True

        if turn.execution_policy == "auto":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.force_approval = True
        # edit: both flags False → normal approval flow

        _MODE_PROMPTS = {
            "plan": (
                "【Agent 模式：规划 — 只读分析】你的角色是分析助手。"
                "你可以使用只读工具（搜索、读文件、查看代码）获取信息、分析问题、提供方案和建议。\n"
                "限制：不能修改文件，不能执行会改变环境的命令，不能创建或删除资源。\n"
                "请在回答中充分利用搜索、阅读等只读工具来获取信息并给出分析。"
                "如果用户请求修改，请描述修改方案和步骤，"
                "等待用户切换到「允许编辑」或「自动」模式后再执行。\n\n"
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

        # ── Local skill index (issue #613) ───────────────────────────
        # Surface the workspace/builtin skill inventory in the system
        # prompt so the model can discover local skills during planning
        # instead of denying their existence from training priors
        # ("没有名为 xxx 的现成 Agent"). Progressive disclosure: only
        # name + description + location; the full SKILL.md is loaded on
        # demand via skill_manage view / read_file. Best-effort: a scan
        # failure must never break the turn.
        try:
            from miqi.agent.skills import SkillsLoader

            loader = SkillsLoader(self.services.workspace)
            # Single scan per turn, shared by the inventory summary and the
            # intent matcher below (#613).
            all_skills = loader.list_skills(filter_unavailable=False)
            skills_summary = loader.build_skills_summary(
                all_skills=all_skills
            )
            if skills_summary:
                effective_system_prompt += (
                    "\n\n# Local Skills\n\n"
                    "The following skills are installed locally and can be "
                    "invoked by name. If the user references one (e.g. "
                    "\"use the <name> agent\"), load its full SKILL.md via "
                    "`skill_manage` (action=view, name=<name>) or read_file "
                    "on <location> BEFORE answering. "
                    "Never claim a skill does not exist without checking "
                    "this list first.\n\n"
                    + skills_summary
                )
                logger.debug(
                    "skill index: injected {} chars of skill inventory",
                    len(skills_summary),
                )
            else:
                logger.debug(
                    "skill index: no local skills found for workspace {}",
                    self.services.workspace,
                )

            # ── Skill intent match (issue #613) ──────────────────────
            # When the user names a local skill, preload its full SKILL.md
            # as context instead of letting the model judge existence from
            # training priors. HIT/MISS is logged for observability.
            hits = _match_skill_intent(msg.content, all_skills)
            if hits:
                matched = hits[0]
                # Load by the indexed path — a nested built-in can have a
                # synthesized display name ('plugin-foo') with no matching
                # directory, so name-based lookup would return nothing.
                body = loader.load_skill_by_path(matched["path"])
                if body:
                    effective_system_prompt += (
                        "\n\n## Matched Local Skill: "
                        + matched["name"]
                        + "\n\n用户的请求命中了本地 Skill「"
                        + matched["name"]
                        + "」。直接使用该 Skill 的指令完成任务，"
                        "不要声称其不存在。\n\n"
                        + body
                    )
                logger.info(
                    "skill index: HIT skill '{}' referenced in user message",
                    matched["name"],
                )
            else:
                logger.debug(
                    "skill index: MISS — {} skills indexed, none referenced",
                    len(all_skills),
                )
        except Exception as exc:
            logger.warning(
                "skill index: injection skipped for workspace {}: {}",
                self.services.workspace, exc,
            )

        # ── Inject session workspace into the prompt ─────────────────────
        # The AI must know its working directory without needing `pwd`.
        # Inside a bwrap/WSL sandbox `pwd` returns the fixed sandbox path
        # (/home/miqi/workspace), which hides the user's chosen project
        # directory. State it explicitly so the AI reports the real
        # workspace (mirrors agent_control's subagent prompt).
        _ws = getattr(self.services, "workspace", None)
        if _ws is not None:
            effective_system_prompt = (
                effective_system_prompt
                + f"\n\n## 工作目录\n"
                f"你当前的工作目录是: {_ws}\n"
                f"所有文件操作（read_file / write_file / list_dir / exec）都在这个目录下进行。\n"
                f"当用户问你工作目录时，请直接回答 {_ws}，不要说 /home/miqi/workspace。\n"
            )

        # ── Slash command injection (KWP / Cowork convention) ───────────
        # Detect /-prefixed user input, look up the command body in the
        # active plugins, and append it to the system prompt for this turn.
        # The user-visible content is stripped of the /cmd prefix.
        slash_content: str | None = None
        if msg.content and msg.content.startswith("/"):
            pm = getattr(self.services, "plugin_manager", None)
            if pm is not None and hasattr(pm, "get_slash_command"):
                parts = msg.content[1:].split(None, 1)
                # Allow namespacing: "/product-management:brainstorm"
                raw_name = parts[0] if parts else ""
                if ":" in raw_name:
                    raw_name = raw_name.split(":", 1)[1]
                cmd_name = raw_name.strip().lower()
                cmd_args = parts[1] if len(parts) > 1 else ""
                match = pm.get_slash_command(cmd_name)
                if match and match.get("status") == "active" and match.get("body"):
                    slash_content = match["body"]
                    if cmd_args:
                        slash_content += "\n\n## User arguments\n\n" + cmd_args
                    # Strip /cmd from the user-visible content.
                    msg = dataclasses.replace(
                        msg,
                        content=cmd_args if cmd_args else "(command invoked without arguments)",
                    )
                    logger.info(
                        "slash command invoked: /{} from plugin {}",
                        cmd_name,
                        match.get("plugin", "?"),
                    )
        if slash_content:
            effective_system_prompt = (
                effective_system_prompt
                + "\n\n## Active Slash Command\n\n"
                + slash_content
            )

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
            # Issue #402: write JSONL FIRST so sessions.get (which reads
            # JSONL) sees the message even if a crash occurs before the
            # SQLite write completes.  The JSONL store is the legacy
            # single-source-of-truth for session overview; SQLite is
            # thread-scoped and recoverable from JSONL if needed.
            await self._save_to_session_manager(
                role="user", content=msg.content)
            if history_runtime is not None:
                await history_runtime.append_message(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    role="user",
                    content=msg.content,
                    payload={"message_fields": payload_fields},
                )
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

                # Issue #402: write JSONL FIRST so sessions.get sees the
                # message even if SQLite write fails later.  Forward all
                # extra fields (tool_calls, name, tool_call_id, etc.) so
                # the frontend can reconstruct file operations.
                await self._save_to_session_manager(
                    role=role, content=content, **extra_fields,
                )

                if history_runtime is not None:
                    await history_runtime.append_message(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        role=role,
                        content=content,
                        payload={"message_fields": extra_fields},
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
            # provider's own message.
            #
            # Issue #529: a raw SDK exception that escaped retry (e.g. via a
            # streaming path that raised instead of yielding a terminal
            # finish_reason="error" event) is NOT a ProviderError, so the old
            # `prov_err = exc if isinstance(exc, ProviderError) else None`
            # collapsed it to error_kind=None / recoverable=False and showed
            # the generic message even for TRANSIENT (503/overload) failures.
            # Re-classify at this final boundary so the category + a useful
            # message survive — the metadata leak is fixed without changing
            # with_retry's / providers' exception contract. Re-wrap into a
            # ProviderError view so the mapping below stays uniform.
            from miqi.providers.resilience import ErrorKind, ProviderError
            if isinstance(exc, ProviderError):
                prov_err = exc
            else:
                prov_err = ProviderError(kind=_classify_chain(exc), message=str(exc))
            error_kind = prov_err.kind.value
            recoverable = prov_err.recoverable
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
            #
            # Issue #529: TRANSIENT (503/overload/conn-reset retries exhausted)
            # is recoverable but the raw SDK text may leak URLs/paths/tokens,
            # so surface a fixed, non-leaking message (same posture as AUTH)
            # rather than prov_err.message. The wording avoids sanitizeUiMessage
            # replacement keywords ("connection error"/"timed out") so it
            # reaches the UI verbatim.
            logger.error("Agent processing error in turn {}: {}", turn_id, exc, exc_info=True)
            user_message = "处理消息时发生内部错误，请重试。"
            if prov_err.kind is ErrorKind.AUTH:
                # AUTH is sensitive — surface a fixed, non-leaking message
                # instead of the raw provider exception text (Plan 58.2).
                user_message = "模型服务认证失败，请检查 Provider 的 API Key、API Base 或当前模型配置。"
            elif prov_err.kind is ErrorKind.PAYMENT_REQUIRED:
                # Issue #528: 402 / balance / quota exhausted — account
                # status, not auth. Fixed non-leaking billing hint
                # (never the raw text), recoverable=False.
                user_message = "模型服务账户余额不足或额度已用尽，请充值或检查账户额度后重试。"
            elif prov_err.kind is ErrorKind.TRANSIENT:
                user_message = "模型服务暂时不可用或过载，请稍后重试。"
            elif prov_err.kind in (
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
