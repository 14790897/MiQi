"""Turn runner — the runtime-owned provider.chat + tool loop.

Historical: Extracted from the legacy AgentLoop._run_agent_loop. Executes a
single turn: calls the provider, routes tool calls through ToolRuntime,
builds messages through ContextRuntime, and returns TurnResult.

Also provides run_agent_job() for AgentJobRuntime — a simplified
single-turn execution path for sub-agent jobs.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from miqi.execution.hook_runtime import (
    HookPoint,
    HookRuntime,
    LifecycleHookContext,
)
from miqi.execution.orchestrator import OrchestrationResult
from miqi.utils.tool_text_guard import (
    LEAK_NOTICE,
    sanitize_tool_call_text,
    tool_names_from_definitions,
)

# Feedback sent back to the model when it writes a tool call as plain text
# instead of using the tool-calling interface. Never executed — the model
# is asked to retry through the real interface (issue #532).
_TOOL_CALL_TEXT_FEEDBACK = (
    "你刚才把工具调用写成了普通文本（如 functions.xxx(...)），"
    "它没有被执行。请改用工具调用接口重新发起，不要把它写成文字。"
)


def _strip_leak_notice(text: str) -> str:
    """Drop the internal LEAK_NOTICE placeholder before persisting to history.

    The notice is a model-facing signal (tool_text_guard), not user content;
    reconstructing history from a stored copy must not show it.
    """
    return text.replace(LEAK_NOTICE, "").strip() if LEAK_NOTICE in text else text


@dataclass
class TurnResult:
    """Result of a completed turn."""
    final_content: str
    messages: list[dict[str, Any]]
    tools_used: list[str]
    token_usage: dict[str, int] = field(default_factory=dict)
    messages_delta: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str | None = None


class TurnRunner:
    """Runs a single model+tool turn.

    Owns provider, tool/context runtimes, event emitter, and iteration cap.
    Stateless per-call — created once per session, reused across turns.
    """

    def __init__(
        self,
        *,
        provider: Any,
        tool_runtime: Any,
        context_runtime: Any,
        event_emitter: Any,
        max_iterations: int,
        capability_resolver: Any | None = None,
        ledger_runtime: Any | None = None,
        hooks: HookRuntime | None = None,
    ):
        self._provider = provider
        self._tools = tool_runtime
        self._context = context_runtime
        self._events = event_emitter
        self._max_iterations = max_iterations
        self._capability_resolver = capability_resolver
        self._ledger = ledger_runtime
        self._hooks = hooks

    async def run(
        self,
        *,
        turn: Any,
        user_content: str,
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
        history: list[dict[str, Any]] | None = None,
        cancel_event: Any | None = None,
        steer_queue: Any | None = None,
        max_iterations: int | None = None,
    ) -> TurnResult:
        """Execute a full turn: model calls until final response or max iters.

        Phase 14 follow-up: checks cancel_event (asyncio.Event) at each
        iteration and yields with CancelledError when set.
        Phase 41: drains steer_queue at safe boundaries and continues
        the same turn instead of completing immediately.

        Phase 51.3: fires PROMPT_SUBMIT, TURN_START, and TURN_END lifecycle hooks.

        *max_iterations* overrides the session-wide iteration cap for this
        call (e.g. sub-agents get a tighter 15-step limit — issue #246).
        """
        lifecycle_ctx = LifecycleHookContext(
            hook_point=HookPoint.PROMPT_SUBMIT,
            data={
                "turn_id": turn.turn_id,
                "thread_id": turn.thread_id,
                "user_content": user_content,
            },
        )
        if self._hooks is not None:
            await self._hooks.run(HookPoint.PROMPT_SUBMIT, lifecycle_ctx)
            lifecycle_ctx.hook_point = HookPoint.TURN_START
            await self._hooks.run(HookPoint.TURN_START, lifecycle_ctx)

        try:
            return await self._run_impl(
                turn=turn,
                user_content=user_content,
                system_prompt=system_prompt,
                tools=tools,
                history=history,
                cancel_event=cancel_event,
                steer_queue=steer_queue,
                max_iterations=max_iterations,
            )
        finally:
            if self._hooks is not None:
                end_ctx = LifecycleHookContext(
                    hook_point=HookPoint.TURN_END,
                    data={
                        "turn_id": turn.turn_id,
                        "thread_id": turn.thread_id,
                        "user_content": user_content,
                    },
                )
                await self._hooks.run(HookPoint.TURN_END, end_ctx)

    async def _run_impl(
        self,
        *,
        turn: Any,
        user_content: str,
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
        history: list[dict[str, Any]] | None = None,
        cancel_event: Any | None = None,
        steer_queue: Any | None = None,
        max_iterations: int | None = None,
    ) -> TurnResult:
        """Core turn loop implementation."""
        # #729: first-token observability — log latency from turn start to the
        # first streamed delta (content or reasoning)，使端到端首字延迟可观测。
        _turn_started = time.perf_counter()
        _first_token_logged = False

        messages = self._context.build_initial_messages(
            turn=turn,
            user_content=user_content,
            system_prompt=system_prompt,
            history=history,
        )
        tools_used: list[str] = []
        tool_text_leaked = False
        # Phase 17: accumulate messages added during this turn for persistence.
        # Each entry is a provider-compatible {role, content, ...} dict.
        messages_delta: list[dict[str, Any]] = []
        # Effective iteration cap — caller override wins over the session-wide
        # limit; report the same value the loop actually uses.
        _effective_iterations = max_iterations or self._max_iterations

        # Accumulate reasoning across all tool-call cycles within the turn so
        # the frontend can show a single merged ThinkBlock. #539
        turn_level_reasoning_parts: list[str] = []

        async def _drain_steer_messages() -> list[dict[str, Any]]:
            if steer_queue is None:
                return []
            drained: list[dict[str, Any]] = []
            while True:
                try:
                    drained.append(steer_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            return drained

        for _iteration in range(_effective_iterations):
            # Phase 14 follow-up: check cancellation before expensive work
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError("Turn cancelled via AbortTurn")

            # Phase 56: hard-trim messages before provider call so we never
            # send a request that exceeds the model's input token limit.
            messages = self._context.trim_for_model(messages, turn.model)

            # Phase 20: prefer streaming. stream_chat() is a base-class
            # method on LLMProvider so every provider supports it — the
            # default wraps chat() and yields a single "completed" event.
            response: Any = None
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            async for stream_event in self._provider.stream_chat(
                messages=messages,
                tools=tools,
                model=turn.model,
                temperature=turn.temperature,
                max_tokens=turn.max_tokens,
            ):
                # Phase 14 follow-up: the iteration-start check above only fires
                # BETWEEN iterations.  A single-shot reply is one iteration, so
                # once the stream is flowing an abort would otherwise be ignored
                # until the whole response finishes (#542).  Check on every
                # stream event so an interrupt stops the bubble mid-generation.
                if cancel_event is not None and cancel_event.is_set():
                    raise asyncio.CancelledError("Turn cancelled via AbortTurn")
                if stream_event.kind == "content_delta":
                    if not _first_token_logged:
                        _first_token_logged = True
                        logger.info(
                            "turn_runner: first_token_latency_ms={:.0f} for turn={}",
                            (time.perf_counter() - _turn_started) * 1000, turn.turn_id,
                        )
                    content_parts.append(stream_event.delta)
                    from miqi.protocol.events import AgentMessageDeltaEvent
                    await self._events.emit(AgentMessageDeltaEvent(
                        turn_id=turn.turn_id,
                        delta=stream_event.delta,
                        index=len(content_parts) - 1,
                    ))
                    if self._ledger is not None:
                        await self._ledger.append_item(
                            thread_id=turn.thread_id,
                            turn_id=turn.turn_id,
                            item_type="assistant_delta",
                            content=stream_event.delta,
                            payload={"index": len(content_parts) - 1},
                        )
                elif stream_event.kind == "reasoning_delta":
                    if not _first_token_logged:
                        _first_token_logged = True
                        logger.info(
                            "turn_runner: first_token_latency_ms={:.0f} for turn={} (reasoning)",
                            (time.perf_counter() - _turn_started) * 1000, turn.turn_id,
                        )
                    reasoning_parts.append(stream_event.delta)
                    from miqi.protocol.events import AgentReasoningEvent
                    logger.info(
                        "turn_runner: got reasoning_delta len={} for turn={}",
                        len(stream_event.delta), turn.turn_id,
                    )
                    await self._events.emit(AgentReasoningEvent(
                        turn_id=turn.turn_id,
                        content=stream_event.delta,
                    ))
                    if self._ledger is not None:
                        await self._ledger.append_item(
                            thread_id=turn.thread_id,
                            turn_id=turn.turn_id,
                            item_type="reasoning_delta",
                            content=stream_event.delta,
                            payload={},
                        )
                elif stream_event.kind == "completed":
                    response = stream_event.response

            # Safety net: if the stream never yielded a completed event,
            # synthesize one from the accumulated content parts.
            if response is None:
                from miqi.providers.base import LLMResponse
                response = LLMResponse(
                    content="".join(content_parts),
                    finish_reason="stop",
                )
            # Phase 57: surface provider-reported failures. A terminal
            # response with finish_reason == "error" means the provider hit
            # an unrecoverable error (transient/rate-limit retries already
            # exhausted by plan/56). Treat it as a real failure — raise a
            # classified ProviderError instead of returning the error text
            # as a normal final_content. Invalid/missing error_kind → FATAL.
            if getattr(response, "finish_reason", None) == "error":
                from miqi.providers.resilience import ErrorKind, ProviderError
                raw_kind = getattr(response, "error_kind", None)
                try:
                    kind = ErrorKind(raw_kind) if raw_kind else ErrorKind.FATAL
                except ValueError:
                    kind = ErrorKind.FATAL
                raise ProviderError(
                    kind=kind,
                    message=response.content or "Provider error",
                )

            # Reasoning content from thinking models (DeepSeek-R1 / Kimi).
            # Prefer the provider-assembled full reasoning on the completed
            # response; fall back to deltas we accumulated ourselves.
            reasoning_content = (
                getattr(response, "reasoning_content", None)
                or "".join(reasoning_parts)
                or None
            )
            if reasoning_content:
                logger.info(
                    "turn_runner: reasoning for turn={} len={}",
                    turn.turn_id, len(reasoning_content),
                )
                # Accumulate turn-level reasoning so the UI can show a single
                # merged ThinkBlock across multiple tool-call cycles. #539
                turn_level_reasoning_parts.append(reasoning_content)

            if not response.has_tool_calls:
                # Phase 41: drain steering messages before completing
                steers = await _drain_steer_messages()
                if steers:
                    # Save assistant reply before steering messages
                    content = response.content or ""
                    content, _ = sanitize_tool_call_text(
                        content, tool_names_from_definitions(tools)
                    )
                    messages = self._context.add_assistant_message(
                        messages=messages,
                        content=content,
                        reasoning_content=reasoning_content,
                    )
                    delta_assistant: dict[str, Any] = {
                        "role": "assistant",
                        "content": _strip_leak_notice(content),
                    }
                    if reasoning_content:
                        delta_assistant["reasoning_content"] = reasoning_content
                    messages_delta.append(delta_assistant)
                    for steer in steers:
                        steer_content = steer["content"]
                        messages.append({"role": "user", "content": steer_content})
                        delta: dict[str, Any] = {
                            "role": "user",
                            "content": steer_content,
                        }
                        cid = steer.get("client_user_message_id")
                        if cid is not None:
                            delta["client_user_message_id"] = cid
                        if steer.get("input_items"):
                            delta["input_items"] = steer["input_items"]
                        messages_delta.append(delta)
                    continue

                content = response.content or ""
                content, was_modified = sanitize_tool_call_text(
                    content, tool_names_from_definitions(tools)
                )
                if was_modified:
                    # The model wrote a tool call as plain text instead of
                    # using the tool-calling interface. The text is never
                    # executed (tool_text_guard), so feed the feedback back
                    # to the model and let it retry properly instead of
                    # ending the turn with an internal placeholder. The
                    # feedback message stays in the model context but is not
                    # persisted (messages_delta) — it is not user content.
                    tool_text_leaked = True
                    messages = self._context.add_assistant_message(
                        messages=messages,
                        content=content,
                    )
                    messages_delta.append({
                        "role": "assistant",
                        "content": _strip_leak_notice(content),
                    })
                    messages.append({"role": "user", "content": _TOOL_CALL_TEXT_FEEDBACK})
                    continue

                # Merge all collected turn-level reasoning into one payload for
                # the frontend so tool-call loops don't produce stacked blocks.
                merged_reasoning = (
                    "\n\n---\n\n".join(turn_level_reasoning_parts).strip()
                    or None
                )
                messages = self._context.add_assistant_message(
                    messages=messages,
                    content=content,
                    reasoning_content=merged_reasoning,
                )
                # Append final assistant message to delta
                delta_final: dict[str, Any] = {
                    "role": "assistant",
                    "content": _strip_leak_notice(content),
                }
                if merged_reasoning:
                    delta_final["reasoning_content"] = merged_reasoning
                messages_delta.append(delta_final)
                return TurnResult(
                    final_content=content,
                    messages=messages,
                    tools_used=tools_used,
                    token_usage=getattr(response, "usage", {}) or {},
                    messages_delta=messages_delta,
                    reasoning=merged_reasoning,
                )

            # #646-v2 (GPT 拍板): harness 任务边界——模型规划输出后、第一个工具
            # 执行前强制计划确认（Agent execution planning boundary）。
            # 模型主动弹过 ask_user_plan_confirm 则不重复；自动模式非阻塞不等待。
            # 实测修正：模型分批调工具（每轮 1-2 个）——按 turn 累计工具名判定
            # 复杂度，避免每轮单独判定永不达阈值（只有审批弹）。
            if not getattr(turn, "_plan_confirm_done", False):
                # GPT 第二轮：累计 phase_history（跨轮阶段检测——任务升级 READ→WRITE）
                phases = list(getattr(turn, "_plan_phases", []))
                seen_names = list(getattr(turn, "_plan_seen_tools", set()))
                for tc in response.tool_calls:
                    from miqi.execution.task_policy import phase_for_tool
                    ph = phase_for_tool(tc.name)
                    if ph:
                        phases.append(ph)
                    if tc.name not in seen_names:
                        seen_names.append(tc.name)
                turn._plan_phases = phases
                turn._plan_seen_tools = set(seen_names)
                from miqi.execution.task_policy import (
                    should_plan_confirm,
                    should_show_timeline,
                    tool_risk,
                )
                policy = getattr(turn, "execution_policy", "edit")
                if "ask_user_plan_confirm" not in seen_names:
                    if policy == "auto":
                        # GPT P0-3：Auto 模式非阻塞 Timeline（复杂任务展示——
                        # always visible 分级；不等待用户）
                        if (
                            should_show_timeline(
                                seen_names,
                                produces_artifact=any(
                                    tool_risk(t) >= 2 for t in seen_names
                                ),
                                phase_history=phases,
                            )
                            and not getattr(turn, "_plan_timeline_shown", False)
                        ):
                            await self._emit_timeline(turn, seen_names)
                            turn._plan_timeline_shown = True
                    elif should_plan_confirm(
                        seen_names,
                        mode=policy,
                        produces_artifact=any(
                            tool_risk(t) >= 2 for t in seen_names
                        ),
                        phase_history=phases,
                    ):
                        confirmed = await self._harness_plan_confirm(turn, seen_names)
                        turn._plan_confirm_done = True
                        if not confirmed:
                            # 用户未确认计划 → 终止本轮，不执行任何工具
                            from miqi.protocol.events import AgentMessageEvent
                            await self._events.emit(AgentMessageEvent(
                                turn_id=turn.turn_id,
                                content="已取消任务：用户未确认执行计划。",
                            ))
                            return TurnResult(
                                final_content="已取消任务：用户未确认执行计划。",
                                messages=messages,
                                tools_used=[],
                                token_usage={},
                                messages_delta=[{"role": "assistant", "content": "已取消任务：用户未确认执行计划。"}],
                                reasoning=None,
                            )

            # ── v3.3 Step 3：确认后冻结 PlanSnapshot + 初始化 TodoState ──
            # （Plan 步骤 → plan-kind Todo（QUEUED）——模型后续用 todo_write 增量更新）
            # 条件：本 turn 弹卡且用户确认（_plan_confirm_done=True）——纯读任务不创建
            if getattr(turn, "_plan_confirm_done", False) and not getattr(turn, "_run_ctx", None):
                import re

                from miqi.execution.task_policy import plan_card_steps
                from miqi.runtime.task_objects import (
                    AgentRunContext,
                    ApprovedScope,
                    PlanSnapshot,
                )

                steps_raw = plan_card_steps([(n, "") for n in seen_names])
                steps: list[tuple[str, str]] = []
                used_ids: set[str] = set()
                for st in steps_raw:
                    text = str(st.get("name") or st.get("title") or "步骤")
                    base = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text.lower()).strip("-") or "step"
                    sid = base
                    i = 2
                    while sid in used_ids:
                        sid = f"{base}-{i}"
                        i += 1
                    used_ids.add(sid)
                    steps.append((sid, text))
                ctx = AgentRunContext(session_key=str(getattr(turn, "session_key", "") or ""))
                ctx.plan_snapshot = PlanSnapshot(
                    plan_id=f"plan-{turn.turn_id[:8]}",
                    goal=str(getattr(turn, "user_content", "") or "")[:60],
                    steps=steps,
                    approved_scope=ApprovedScope(
                        sources=[],
                        artifacts=[],
                        external_actions=[{"provider": "qraft", "operation": "upload"}]
                        if any("upload" in n for n in seen_names)
                        else [],
                    ),
                )
                ctx.todo_state.initialize_from_plan(steps)
                turn._run_ctx = ctx

                # v3.3 Step 6：确认后注入 todo_write 引导（SHOULD——不强制；
                # 带步骤 id 清单——模型才能用 todo_write 更新正确条目）
                todo_ids = "\n".join(f"- {sid}: {text}" for sid, text in steps)
                messages.append({
                    "role": "system",
                    "content": (
                        "你的任务计划已被用户批准并初始化。\n"
                        f"已批准步骤（id: 内容）：\n{todo_ids}\n"
                        "用 todo_write 维护执行进度：开始执行某步前先把它标记为 "
                        "in_progress，完成后标记 completed；等待用户输入/权限/外部资源时"
                        "标记 blocked（附 blocked_reason）。每次只发送变化的步骤。"
                    ),
                })

            # Phase 24: record tool call starts in ledger
            if self._ledger is not None:
                for tc in response.tool_calls:
                    await self._ledger.append_item(
                        thread_id=turn.thread_id,
                        turn_id=turn.turn_id,
                        item_type="tool_call_started",
                        payload={
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "arguments": getattr(tc, "arguments", None),
                        },
                    )

            from miqi.protocol.events import ToolCallBeginEvent, ToolCallEndEvent

            for tc in response.tool_calls:
                await self._events.emit(ToolCallBeginEvent(
                    turn_id=turn.turn_id,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    tool_display=self._format_tool_hint(tc.name, tc.arguments),
                    arguments=tc.arguments,
                ))

            # Execute tool calls concurrently through ToolRuntime
            # v3.3 Step 5：todo_write 特殊处理——进度协议（不注册表执行，
            # 用 turn._run_ctx.todo_state；无上下文 → 提示计划未确认）
            todo_calls = [tc for tc in response.tool_calls if tc.name == "todo_write"]
            other_calls = [tc for tc in response.tool_calls if tc.name != "todo_write"]
            contexts = []
            if todo_calls:
                import json as _json

                from miqi.agent.tools.todo_write import TodoWriteTool

                run_ctx = getattr(turn, "_run_ctx", None)
                for tc in todo_calls:
                    tool = TodoWriteTool(run_ctx.todo_state if run_ctx is not None else None)
                    try:
                        raw_args = getattr(tc, "arguments", None)
                        args = _json.loads(raw_args) if isinstance(raw_args, str) and raw_args else (raw_args or {})
                        result_text = await tool.execute(**args)
                    except Exception as exc:  # pragma: no cover - defensive
                        result_text = _json.dumps({"status": "error", "reason": str(exc)[:120]}, ensure_ascii=False)
                    contexts.append(OrchestrationResult(
                        tool_call_id=tc.id,
                        result=result_text,
                        status=OrchestrationResult.SUCCESS,
                        duration_ms=0,
                    ))
            if other_calls:
                contexts.extend(await self._tools.execute_many(turn, other_calls))

            for tc, ctx in zip(response.tool_calls, contexts):
                result_text = ctx.result or ""
                # paper_search / web_search: keep full result so frontend can
                # render result cards on the live tool row (#539)
                # other tools: truncate to 200 chars for preview
                if tc.name in ("paper_search", "web_search"):
                    output_preview = result_text
                else:
                    output_preview = result_text[:200]
                await self._events.emit(ToolCallEndEvent(
                    turn_id=turn.turn_id,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    success=ctx.status == OrchestrationResult.SUCCESS,
                    output_preview=output_preview,
                    output_size=len(result_text),
                    duration_ms=getattr(ctx, "duration_ms", 0),
                ))

            # Phase 24: record tool call completions in ledger
            if self._ledger is not None:
                for ctx in contexts:
                    await self._ledger.append_item(
                        thread_id=turn.thread_id,
                        turn_id=turn.turn_id,
                        item_type="tool_call_completed",
                        payload={
                            "tool_call_id": getattr(ctx, "tool_call_id", ""),
                            "result": getattr(ctx, "result", None),
                            "duration_ms": getattr(ctx, "duration_ms", 0),
                            "retry_count": getattr(ctx, "retry_count", 0),
                            "permission_verdict": (
                                ctx.permission_decision.verdict.value
                                if getattr(ctx, "permission_decision", None) is not None
                                else None
                            ),
                            "sandbox_type": (
                                ctx.sandbox_selection.sandbox_type.value
                                if getattr(ctx, "sandbox_selection", None) is not None
                                else None
                            ),
                        },
                    )

            # 1. Build assistant tool-call entries (no message mutation yet)
            assistant_tool_calls: list[dict[str, Any]] = []
            for tool_call in response.tool_calls:
                tools_used.append(tool_call.name)
                assistant_tool_calls.append({
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": (
                            tool_call.arguments_json
                            if hasattr(tool_call, "arguments_json")
                            else json.dumps(
                                getattr(tool_call, "arguments", {}) or {},
                                ensure_ascii=False,
                            )
                        ),
                    },
                })

            # 2. Assistant message with tool_calls MUST precede tool results
            _asst_content = response.content or ""
            _asst_content, _content_modified = sanitize_tool_call_text(
                _asst_content, tool_names_from_definitions(tools)
            )
            if _content_modified:
                # The model DID issue the real tool call above — a text-form
                # echo in the content is noise. Drop the internal placeholder
                # entirely instead of rendering it to the user.
                _asst_content = _asst_content.replace(LEAK_NOTICE, "").strip()
            messages = self._context.add_assistant_message(
                messages=messages,
                content=_asst_content,
                tool_calls=assistant_tool_calls,
                reasoning_content=reasoning_content,
            )
            # Persist assistant(tool_calls) in messages_delta
            asst_delta: dict[str, Any] = {
                "role": "assistant",
                "content": _asst_content or None,
                "tool_calls": assistant_tool_calls,
            }
            if reasoning_content:
                asst_delta["reasoning_content"] = reasoning_content
            messages_delta.append(asst_delta)

            # 3. Append tool results in order (assistant → tool → tool → …)
            for tool_call, ctx in zip(response.tool_calls, contexts):
                messages = self._context.add_tool_result(
                    messages=messages,
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    content=ctx.result or "",
                    arguments=tool_call.arguments,
                )
                # Persist tool result in messages_delta
                messages_delta.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.name,
                    "content": ctx.result or "",
                    "arguments": tool_call.arguments,
                })
        # Exhausted iterations — issue #491: surface why the loop never
        # converged instead of returning a bare generic message.
        diagnosis = self._build_exhaustion_diagnosis(messages)
        content = (
            f"已达到最大迭代次数（{_effective_iterations}）。"
            f"已使用工具：{', '.join(dict.fromkeys(tools_used)) or '无'}。"
            f"请将任务拆分为更小的步骤重试。\n\n"
            f"【失败诊断】\n{diagnosis}"
        )
        if tool_text_leaked:
            content += (
                "\n\n另外，模型多次把工具调用写成了文本（如 functions.xxx(...)），"
                "这些调用未被执行。请重试或换一种表述。"
            )
        messages_delta.append({"role": "assistant", "content": content})
        return TurnResult(
            final_content=content,
            messages=messages,
            tools_used=tools_used,
            messages_delta=messages_delta,
        )

    async def run_agent_job(self, job: Any) -> TurnResult:
        """Run a sub-agent job through TurnRunner.

        Builds a TurnContext from the job metadata, resolves tools
        via the CapabilityResolver if available, and executes a
        single turn. Used by AgentJobRuntime._run().
        """
        from pathlib import Path

        from miqi.runtime.agent_registry import AgentRegistry
        from miqi.runtime.turn_context import TurnContext

        metadata = AgentRegistry().resolve(job.agent_type)
        turn = TurnContext(
            turn_id=job.job_id,
            agent_metadata=metadata,
            thread_id=job.thread_id,
            workspace=getattr(self._provider, "workspace", Path(".")),
            model=self._provider.get_default_model(),
            provider=self._provider,
            execution_policy="edit",  # sub-agents default to normal approval flow
            temperature=0.1,
            max_tokens=8192,
        )

        # Resolve capabilities if available (Phase 13)
        if self._capability_resolver is not None:
            capabilities = self._capability_resolver.resolve(agent_metadata=metadata)
            turn.capabilities = capabilities
            tools = capabilities.tool_definitions
        else:
            tools = []

        # Execution policy — controls agent autonomy level
        # Three-layer: system prompt + tool set + approval flags.
        # Plan: strategist — read-only, proposes approach
        # Manual: collaborator — all tools, each step confirmed by user
        # Edit: developer — all tools, safe auto, dangerous ask
        # Auto: agent — all tools, bypass approval entirely

        from miqi.runtime.tool_policy import PLAN_BLOCKED_TOOLS

        if turn.execution_policy == "plan":
            tools = [t for t in tools if t.get("name") not in PLAN_BLOCKED_TOOLS]
            turn.bypass_approval = True  # plan mode tools are safe, deny-list still wins
        elif turn.execution_policy == "ask":
            # Legacy ask mode — filter write/exec tools
            tools = [t for t in tools if t.get("name") not in PLAN_BLOCKED_TOOLS]
        # manual / edit / auto: all tools available,
        # differentiation happens at approval layer

        if turn.execution_policy == "auto":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.bypass_approval = False
            turn.force_approval = True
        elif turn.execution_policy == "edit":
            # #646-v2（GPT 评审）: 协作（允许编辑）模式默认——文件修改自动放行，
            # exec/危险操作仍确认。用户显式设置过权限（permission_profile 非 None）
            # 时尊重用户设置。
            turn.bypass_approval = False
            if getattr(turn, "permission_profile", None) is None:
                from miqi.execution.approval_policy import ApprovalMode, ApprovalPolicy
                from miqi.runtime.permission_profile import PermissionProfile

                turn.permission_profile = PermissionProfile(
                    approval_policy=ApprovalPolicy(
                        mode=ApprovalMode.GRANULAR,
                        granular={"file_write": "never"},
                    )
                )
        # edit: both flags False → normal approval flow
        # plan: bypass_approval already set above

        # Issue #246: sub-agents get a tight 15-step iteration cap (the legacy
        # SubagentManager limit), not the session-wide max_tool_iterations.
        SUBAGENT_MAX_ITERATIONS = 15
        return await self.run(
            turn=turn,
            user_content=job.task,
            system_prompt=metadata.system_prompt,
            tools=tools,
            max_iterations=SUBAGENT_MAX_ITERATIONS,
        )

    async def _harness_plan_confirm(
        self, turn: Any, tool_names: list[str]
    ) -> bool:
        """#646-v2: harness 强制计划卡——经 user_input_gate 弹卡等用户确认。

        载荷由 TaskPolicy 生成（用户语言步骤 + 权限推断），不依赖模型写计划。
        返回 True=用户确认开始执行；False=取消/超时。
        """
        from miqi.agent.user_input_resolver import (
            make_resolver,
            user_input_emitter_for,
        )
        from miqi.execution.task_policy import (
            permissions_for_tools,
            plan_card_steps,
        )

        # 无 UI 通道（headless/测试/CLI）→ 降级放行——阻塞会让所有写/执行静默失败。
        # 注意：必须走 thread→session 映射（与 resolver 一致）——直查 thread_id
        # 在 thread≠session 的环境（测试/多会话）会误判无通道而静默放行。
        from miqi.agent.user_input_resolver import session_for_thread

        thread_id = str(getattr(turn, "thread_id", "") or "")
        session_key = session_for_thread(thread_id) or thread_id
        if user_input_emitter_for(session_key) is None:
            return True

        tool_calls_with_hint = [
            (name, "") for name in tool_names
        ]
        resolver = make_resolver()
        goal = str(getattr(turn, "user_content", "") or "")[:60]
        result = await resolver({
            "threadId": turn.thread_id,
            "turnId": turn.turn_id,
            "title": "AI 准备执行任务",
            "goal": goal or "多步骤任务",
            "steps": plan_card_steps(tool_calls_with_hint),
            "permissions": permissions_for_tools(tool_names),
            "timeout_seconds": 300,
        })
        answers = result.get("answers") or {}
        return bool(
            result.get("status") == "submitted"
            and str(answers.get("choice_id", "")) == "confirm"
        )


    async def _emit_timeline(self, turn: Any, tool_names: list[str]) -> None:
        """#646-v2 GPT P0-3：Auto 模式非阻塞 Timeline 展示事件。

        与 _harness_plan_confirm 的区别：**不经过 gate、不等待用户**——
        直接发 user_input_requested（display=timeline），前端渲染无按钮的
        步骤列表（✓⟳○）。payload 与 PlanCard 同构（前端复用渲染）。
        """
        from miqi.agent.user_input_resolver import (
            session_for_thread,
            user_input_emitter_for,
        )
        from miqi.execution.task_policy import (
            permissions_for_tools,
            plan_card_steps,
        )

        thread_id = str(getattr(turn, "thread_id", "") or "")
        session_key = session_for_thread(thread_id) or thread_id
        emitter = user_input_emitter_for(session_key)
        if emitter is None:
            return  # 无 UI 通道（headless/测试）——不展示

        tool_calls_with_hint = [(name, "") for name in tool_names]
        payload = {
            "threadId": thread_id,
            "turnId": getattr(turn, "turn_id", ""),
            "title": "AI 正在执行任务",
            "goal": str(getattr(turn, "user_content", "") or "")[:60] or "多步骤任务",
            "steps": plan_card_steps(tool_calls_with_hint),
            "permissions": permissions_for_tools(tool_names),
            "display": "timeline",  # 前端据此渲染 Timeline（无按钮、不阻塞）
        }
        try:
            if asyncio.iscoroutinefunction(emitter):
                await emitter(payload)
            else:
                emitter(payload)
        except Exception:
            pass  # Timeline 是展示型，失败不影响执行

    @staticmethod
    def _format_tool_hint(name: str, args: dict) -> str:
        """Format a tool call as a concise display hint.

        Path-like and command args show the target value (truncated at 50
        chars); every other arg shows only the parameter name. Values like
        paper titles, URLs, or queries are long strings that would leak
        into the hint instead of a concise call summary (issue #532).
        """
        if not args:
            return name
        for key in ("path", "file_path", "filename", "outPath", "command"):
            val = args.get(key)
            if isinstance(val, str) and val:
                if len(val) > 50:
                    return f'{name}("{val[:50]}…")'
                return f'{name}("{val}")'
        key = next(iter(args), "")
        return f"{name}({key}=…)" if key else name

    # ── Max-iterations diagnosis (issue #491) ──────────────────────────

    #: How many trailing tool results to scan for failure signals when the
    #: turn loop exhausts its iteration budget.
    _DIAGNOSIS_SCAN_TAIL = 8

    @classmethod
    def _extract_failure_signal(cls, name: str, content: str) -> str | None:
        """Extract a one-line failure signal from a single tool result.

        Returns ``None`` when the result carries no failure signal — e.g.
        a successful response the loop still failed to converge on.
        Understands the structured JSON shapes emitted by the built-in
        tools (paper_download/paper_search/paper_get/web_fetch) and the
        plain-text shapes of web_search/exec.
        """
        text = (content or "").strip()
        if not text:
            return None

        payload: Any = None
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            payload = None

        if isinstance(payload, dict):
            error = str(payload.get("error") or "").strip()
            ok = payload.get("ok", True)
            status = payload.get("status_code")
            paywall = bool(payload.get("paywall_suspected"))
            if error:
                detail = error[:160]
                if paywall:
                    detail += "（疑似付费墙/登录/机构访问限制）"
                elif isinstance(status, int) and status >= 400:
                    detail += f"（HTTP {status}）"
                return f"{name}: {detail}"
            if ok is False:
                return f"{name}: 工具报告失败"
            if paywall:
                return f"{name}: 疑似付费墙/登录拦截页"
            if isinstance(status, int) and status >= 400:
                return f"{name}: HTTP {status}"
            if payload.get("items") == [] or payload.get("count") == 0:
                return f"{name}: 未找到结果"
            return None

        # Plain-text results (web_search / exec)
        lowered = text.lower()
        if text.startswith("Error") or text.startswith("错误"):
            return f"{name}: {text[:160]}"
        if text.startswith("No results for") or "没有结果" in text:
            return f"{name}: 未找到结果"
        if "timed out" in lowered or "timeout" in lowered:
            return f"{name}: 请求超时"
        return None

    @classmethod
    def _build_exhaustion_diagnosis(cls, messages: list[dict[str, Any]]) -> str:
        """Build a structured diagnosis for the max-iterations exit path.

        Summarizes tool usage across the whole turn, then scans the
        trailing tool results for concrete failure signals (paywall,
        HTTP errors, empty results, timeouts) so the final message tells
        the user *why* the task failed instead of a bare generic hint.
        """
        tool_counts: dict[str, int] = {}
        tool_msgs: list[dict[str, Any]] = []
        for m in messages:
            if m.get("role") != "tool":
                continue
            name = str(m.get("name") or "未知工具")
            tool_counts[name] = tool_counts.get(name, 0) + 1
            tool_msgs.append(m)

        usage = "、".join(f"{n}×{c}" for n, c in tool_counts.items()) or "无"
        lines = [f"工具调用概况：{usage}"]
        if tool_msgs:
            signals: list[str] = []
            seen: set[str] = set()
            for m in tool_msgs[-cls._DIAGNOSIS_SCAN_TAIL:]:
                sig = cls._extract_failure_signal(
                    str(m.get("name") or ""),
                    str(m.get("content") or ""),
                )
                if sig and sig not in seen:
                    seen.add(sig)
                    signals.append(sig)
            if signals:
                lines.append("最近失败信号：")
                lines.extend(f"- {s}" for s in signals)
            else:
                lines.append(
                    "最近工具调用未返回明确失败信号——任务可能在持续尝试但未取得进展。"
                    "请告知用户当前状态，并建议拆分为更小的步骤或更换检索途径。"
                )
        return "\n".join(lines)
