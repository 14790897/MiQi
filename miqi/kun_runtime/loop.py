"""KUN AgentLoop — core execution engine for the desktop workbench runtime.

Aligns with KUN ``loop/agent-loop.ts``.
Orchestrates the full turn pipeline: drain steering → model_step → tool dispatch → loop.

All dependencies are constructor-injected for testability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from loguru import logger

from miqi.kun_runtime.cancellation import CancellationToken, InflightTracker
from miqi.kun_runtime.compactor import ContextCompactor
from miqi.kun_runtime.event_recorder import RuntimeEventRecorder
from miqi.kun_runtime.model_client import (
    ModelRequest,
    ModelToolSpec,
)
from miqi.kun_runtime.stores import FileSessionStore, FileThreadStore
from miqi.kun_runtime.tool_host import (
    ToolCallLike,
    ToolHostContext,
    ToolHostResult,
)
from miqi.kun_runtime.tool_storm_breaker import ToolStormBreaker
from miqi.kun_runtime.turn_service import TurnService
from miqi.kun_runtime.usage import UsageService

# ═══════════════════════════════════════════════════════════════════════════════
# Options
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class AgentLoopOptions:
    """Dependencies and configuration for the KUN AgentLoop."""

    thread_store: FileThreadStore
    session_store: FileSessionStore
    model: Any  # MiQiModelClient | FakeModelClient
    tool_host: Any  # MiQiToolHost | FakeToolHost
    usage: UsageService
    events: RuntimeEventRecorder
    turns: TurnService
    inflight: InflightTracker
    compactor: ContextCompactor

    now_iso: Any = field(default_factory=lambda: _utc_now_iso)

    # Optional
    approval_gate: Any = None
    user_input_gate: Any = None
    token_economy: dict[str, Any] | None = None
    tool_storm: dict[str, Any] | None = None
    auto_model_router: Any = None


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

PARALLEL_READ_ONLY_TOOL_NAMES = frozenset({"read", "grep", "find", "ls", "read_file", "list_dir", "web_search", "web_fetch", "paper_search", "paper_get"})
MAX_PARALLEL_TOOL_CALLS = 3


# ═══════════════════════════════════════════════════════════════════════════════
# AgentLoop
# ═══════════════════════════════════════════════════════════════════════════════


class AgentLoop:
    """Python implementation of the KUN agent loop.

    Usage::

        loop = AgentLoop(opts)
        status = await loop.run_turn("th1", "t1")
    """

    def __init__(self, opts: AgentLoopOptions):
        self._opts = opts
        self._tool_storm_breakers: dict[str, ToolStormBreaker] = {}

    # ── Public API ──────────────────────────────────────────────────────

    async def run_turn(
        self, thread_id: str, turn_id: str
    ) -> Literal["completed", "failed", "aborted"]:
        """Run a turn end-to-end. Returns the final turn status."""
        token = self._opts.turns.get_abort_token(turn_id)
        if token is None:
            await self._opts.turns.finish_turn(thread_id, turn_id, "failed", error="no abort token")
            return "failed"
        if token.is_set():
            await self._opts.turns.finish_turn(thread_id, turn_id, "aborted")
            return "aborted"

        try:
            if self._opts.tool_storm and self._opts.tool_storm.get("enabled", True):
                self._tool_storm_breakers[turn_id] = ToolStormBreaker(
                    window_size=self._opts.tool_storm.get("windowSize", 8),
                    threshold=self._opts.tool_storm.get("threshold", 3),
                )

            await self._record_pipeline(thread_id, turn_id, "setup")
            await self._record_pipeline(thread_id, turn_id, "pre_start")
            await self._drain_steering(thread_id, turn_id, token)
            await self._record_pipeline(thread_id, turn_id, "post_start")

            status = await self._loop(thread_id, turn_id, token)
            await self._opts.turns.finish_turn(thread_id, turn_id, status)
            return status
        except Exception as exc:
            message = str(exc)
            logger.exception(f"AgentLoop run_turn failed: {message}")
            await self._opts.turns.finish_turn(thread_id, turn_id, "failed", error=message)
            return "failed"
        finally:
            self._tool_storm_breakers.pop(turn_id, None)

    # ── Loop ────────────────────────────────────────────────────────────

    async def _loop(
        self, thread_id: str, turn_id: str, token: CancellationToken
    ) -> Literal["completed", "failed", "aborted"]:
        for step in range(100):  # safety cap
            if token.is_set():
                return "aborted"
            await self._drain_steering(thread_id, turn_id, token)
            result = await self._model_step(thread_id, turn_id, token, step)
            if result == "stop":
                return "completed"
            if result in ("failed", "aborted"):
                return result
        logger.warning(f"Max steps reached for turn {turn_id}")
        return "completed"

    # ── Model Step ──────────────────────────────────────────────────────

    async def _model_step(
        self, thread_id: str, turn_id: str, token: CancellationToken, step_index: int = 0
    ) -> Literal["continue", "stop", "failed", "aborted"]:
        await self._record_pipeline(thread_id, turn_id, "input_received", {"stepIndex": step_index})

        # Load thread and turn
        thread = await self._opts.thread_store.get(thread_id) or {}
        turn = await self._opts.turns.get_turn(thread_id, turn_id) or {}

        # Load and heal history
        loaded_items = await self._opts.session_store.load_items(thread_id)
        await self._record_pipeline(thread_id, turn_id, "input_cached")

        # Resolve model
        model = turn.get("model") or thread.get("model") or getattr(self._opts.model, "model", "deepseek-chat")
        await self._record_pipeline(thread_id, turn_id, "input_routed", {"model": model})

        approval_gate = self._opts.approval_gate

        async def await_approval(payload: dict[str, Any]) -> Literal["allow", "deny"]:
            if approval_gate is None:
                return "allow"
            return await approval_gate.request(
                thread_id,
                turn_id,
                str(payload.get("toolName") or ""),
                str(payload.get("summary") or "Approve tool call"),
                payload,
            )

        # List tools
        tool_context = ToolHostContext(
            thread_id=thread_id,
            turn_id=turn_id,
            workspace=thread.get("workspace", ""),
            thread_mode=thread.get("mode"),
            approval_policy=thread.get("approvalPolicy", "auto"),
            abort_signal=token,
            active_skill_ids=turn.get("activeSkillIds", []),
            await_approval=await_approval if approval_gate is not None else None,
        )
        tools = await self._opts.tool_host.list_tools(tool_context)
        tool_specs = [ModelToolSpec(
            name=t["name"],
            description=t.get("description", ""),
            input_schema=t.get("inputSchema", {}),
            tool_kind=t.get("toolKind"),
        ) for t in tools]

        # Compaction
        history = await self._compact_if_needed(loaded_items, model, token, thread_id, turn_id)
        if token.is_set():
            return "aborted"
        await self._record_pipeline(thread_id, turn_id, "input_compressed", {"historyItems": len(history)})

        # Build model request with mode-specific system prompt
        _MODE_SYSTEM_PROMPTS = {
            "edit": "You are Kun, a careful and helpful AI assistant. Diagnose issues and make changes directly.",
            "plan": (
                "You are Kun, a careful and helpful AI assistant in PLAN mode. "
                "Before making any changes, analyze the user's request and present "
                "a structured plan (file changes + steps). Wait for user confirmation "
                "before executing any write/exec actions."
            ),
            "ask": (
                "You are Kun, a careful and helpful AI assistant in READ-ONLY mode. "
                "You may read files, search code, and analyze — but you MUST NOT "
                "request any tool that writes files, executes commands, or has side effects. "
                "Answer questions thoroughly using only read/search/fetch tools."
            ),
        }
        system_prompt = _MODE_SYSTEM_PROMPTS.get(thread_mode, _MODE_SYSTEM_PROMPTS["edit"])

        request = ModelRequest(
            thread_id=thread_id,
            turn_id=turn_id,
            model=model,
            system_prompt=system_prompt,
            history=history,
            tools=tool_specs,
            temperature=0.1,
            max_tokens=8192,
        )

        # Token economy (optional)
        token_econ = self._opts.token_economy or {}
        if token_econ.get("enabled"):
            from miqi.kun_runtime.token_economy import TOKEN_ECONOMY_INSTRUCTION
            request.context_instructions = request.context_instructions or []
            request.context_instructions.append(TOKEN_ECONOMY_INSTRUCTION)

        await self._record_pipeline(thread_id, turn_id, "pre_send", {
            "model": model, "historyItems": len(history), "toolCount": len(tools),
        })
        await self._record_pipeline(thread_id, turn_id, "post_send", {"model": model})

        # Stream model response
        text_accumulator = ""
        reasoning_accumulator = ""
        completed_tool_calls: list[ToolCallLike] = []
        stop_reason = "stop"

        async for chunk in self._opts.model.stream(request):
            if token.is_set():
                return "aborted"

            if chunk.kind == "assistant_text_delta":
                text_accumulator += chunk.text or ""
                await self._opts.events.record({
                    "kind": "assistant_text_delta",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "itemId": f"item_text_{turn_id}",
                    "item": {
                        "id": f"item_text_{turn_id}",
                        "turnId": turn_id,
                        "threadId": thread_id,
                        "role": "assistant",
                        "status": "running",
                        "kind": "assistant_text",
                        "createdAt": self._opts.now_iso(),
                        "text": chunk.text or "",
                    },
                })

            elif chunk.kind == "assistant_reasoning_delta":
                reasoning_accumulator += chunk.text or ""

            elif chunk.kind == "tool_call_complete":
                call = ToolCallLike(
                    call_id=chunk.callId or "",
                    tool_name=chunk.toolName or "",
                    arguments=chunk.arguments or {},
                )

                # Apply tool storm breaker
                storm = self._tool_storm_breakers.get(turn_id)
                if storm:
                    inspection = storm.inspect(call.tool_name, call.arguments)
                    if inspection["suppress"]:
                        await self._persist_suppressed_tool_call(thread_id, turn_id, call, inspection.get("reason"))
                        continue

                completed_tool_calls.append(call)

                # Persist tool call item
                item_id = f"item_tool_{turn_id}_{call.call_id}"
                await self._opts.turns.apply_item(thread_id, {
                    "id": item_id,
                    "turnId": turn_id,
                    "threadId": thread_id,
                    "role": "assistant",
                    "status": "completed",
                    "kind": "tool_call",
                    "createdAt": self._opts.now_iso(),
                    "toolName": call.tool_name,
                    "callId": call.call_id,
                    "toolKind": "tool_call",
                    "arguments": call.arguments,
                })
                await self._opts.events.record({
                    "kind": "tool_call_ready",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "itemId": item_id,
                    "callId": call.call_id,
                    "toolName": call.tool_name,
                    "readyCount": len(completed_tool_calls),
                })

            elif chunk.kind == "usage":
                usage_snap = self._opts.usage.record(thread_id, chunk.usage or {})
                await self._opts.events.record({
                    "kind": "usage",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "model": model,
                    "usage": usage_snap,
                })

            elif chunk.kind == "completed":
                stop_reason = chunk.stopReason or "stop"

            elif chunk.kind == "error":
                await self._opts.events.record({
                    "kind": "error",
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "message": chunk.message or "Unknown error",
                    "code": chunk.code,
                })
                stop_reason = "error"

        await self._record_pipeline(thread_id, turn_id, "response_received", {
            "stopReason": stop_reason,
            "toolCallCount": len(completed_tool_calls),
        })

        # Persist assistant text item
        if text_accumulator:
            await self._opts.turns.apply_item(thread_id, {
                "id": f"item_text_{turn_id}",
                "turnId": turn_id,
                "threadId": thread_id,
                "role": "assistant",
                "status": "completed",
                "kind": "assistant_text",
                "createdAt": self._opts.now_iso(),
                "finishedAt": self._opts.now_iso(),
                "text": text_accumulator,
            })

        # Persist reasoning if present
        if reasoning_accumulator:
            await self._opts.turns.apply_item(thread_id, {
                "id": f"item_reasoning_{turn_id}",
                "turnId": turn_id,
                "threadId": thread_id,
                "role": "assistant",
                "status": "completed",
                "kind": "assistant_reasoning",
                "createdAt": self._opts.now_iso(),
                "text": reasoning_accumulator,
            })

        if stop_reason == "error":
            return "failed"

        # If no tool calls, we're done
        if not completed_tool_calls:
            return "stop"

        # Dispatch tool calls
        dispatched = await self._dispatch_tool_calls(
            thread_id, turn_id, completed_tool_calls, tool_context, token,
        )
        if dispatched == "aborted":
            return "aborted"
        return "continue"

    # ── Tool Dispatch ───────────────────────────────────────────────────

    async def _dispatch_tool_calls(
        self,
        thread_id: str,
        turn_id: str,
        calls: list[ToolCallLike],
        context: ToolHostContext,
        token: CancellationToken,
    ) -> Literal["continue", "aborted"]:
        index = 0
        while index < len(calls):
            if token.is_set():
                return "aborted"

            call = calls[index]

            # Storm check
            storm = self._tool_storm_breakers.get(turn_id)
            if storm:
                inspection = storm.inspect(call.tool_name, call.arguments)
                if inspection["suppress"]:
                    await self._persist_suppressed_tool_call(thread_id, turn_id, call, inspection.get("reason"))
                    index += 1
                    continue

            # Check if parallel-safe
            if not _is_parallel_safe(call, context.approval_policy):
                result = await self._opts.tool_host.execute(call, context)
                await self._persist_tool_result(thread_id, turn_id, call, result)
                index += 1
                continue

            # Batch parallel-safe calls
            batch: list[ToolCallLike] = [call]
            index += 1
            while len(batch) < MAX_PARALLEL_TOOL_CALLS and index < len(calls):
                next_call = calls[index]
                if not _is_parallel_safe(next_call, context.approval_policy):
                    break
                # Storm check for next
                if storm:
                    ins = storm.inspect(next_call.tool_name, next_call.arguments)
                    if ins["suppress"]:
                        await self._persist_suppressed_tool_call(thread_id, turn_id, next_call, ins.get("reason"))
                        index += 1
                        continue
                batch.append(next_call)
                index += 1

            # Execute batch in parallel
            import asyncio as _asyncio
            tasks = [
                self._opts.tool_host.execute(c, context)
                for c in batch
            ]
            results = await _asyncio.gather(*tasks, return_exceptions=True)
            for batch_call, result in zip(batch, results):
                if isinstance(result, BaseException):
                    logger.error(f"Tool {batch_call.tool_name} failed: {result}")
                    result = ToolHostResult(item={
                        "kind": "tool_result",
                        "id": f"item_{turn_id}_{batch_call.call_id}",
                        "turnId": turn_id,
                        "threadId": thread_id,
                        "role": "tool",
                        "status": "failed",
                        "createdAt": self._opts.now_iso(),
                        "toolName": batch_call.tool_name,
                        "callId": batch_call.call_id,
                        "toolKind": "tool_call",
                        "output": f"Tool execution failed: {result}",
                        "isError": True,
                    })
                await self._persist_tool_result(thread_id, turn_id, batch_call, result)

        return "continue"

    # ── Persistence ─────────────────────────────────────────────────────

    async def _persist_tool_result(
        self, thread_id: str, turn_id: str, call: ToolCallLike, result: ToolHostResult
    ) -> None:
        await self._opts.turns.apply_item(thread_id, result.item)

    async def _persist_suppressed_tool_call(
        self, thread_id: str, turn_id: str, call: ToolCallLike, reason: str | None
    ) -> None:
        item = {
            "kind": "tool_result",
            "id": f"item_{call.call_id}_storm",
            "turnId": turn_id,
            "threadId": thread_id,
            "role": "tool",
            "status": "failed",
            "createdAt": self._opts.now_iso(),
            "toolName": call.tool_name,
            "callId": call.call_id,
            "toolKind": "tool_call",
            "output": reason or "duplicate tool call suppressed by repeat-loop guard",
            "isError": True,
        }
        await self._opts.turns.apply_item(thread_id, item)
        await self._opts.events.record({
            "kind": "tool_storm_suppressed",
            "threadId": thread_id,
            "turnId": turn_id,
            "toolName": call.tool_name,
            "callId": call.call_id,
            "message": reason or "duplicate tool call suppressed",
        })

    # ── Helpers ─────────────────────────────────────────────────────────

    async def _drain_steering(self, thread_id: str, turn_id: str, token: CancellationToken) -> None:
        pending = self._opts.turns.drain_steering(thread_id)
        if not pending:
            return
        for text in pending:
            item = {
                "id": f"item_steered_{_new_id_suffix()}",
                "turnId": turn_id,
                "threadId": thread_id,
                "role": "user",
                "status": "completed",
                "kind": "user_message",
                "createdAt": self._opts.now_iso(),
                "finishedAt": self._opts.now_iso(),
                "text": text,
            }
            await self._opts.turns.apply_item(thread_id, item)

    async def _compact_if_needed(
        self, items: list[dict[str, Any]], model: str, token: CancellationToken,
        thread_id: str, turn_id: str,
    ) -> list[dict[str, Any]]:
        plan = self._opts.compactor.plan_compaction(items, model)
        if plan is None:
            return items
        result = self._opts.compactor.compact(
            thread_id=thread_id,
            turn_id=turn_id,
            history=items,
            pinned_constraints=["user: preserve recent turns"],
            keep_recent=plan["keepRecent"],
            reason=plan["reason"],
            mode=plan["mode"],
        )
        if result["replacedTokens"] > 0:
            await self._opts.session_store.append_item(thread_id, result["summaryItem"])
            await self._opts.events.record({
                "kind": "compaction_completed",
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": result["summaryItem"]["id"],
                "summary": result["summaryItem"]["summary"],
                "replacedTokens": result["replacedTokens"],
            })
        return result["next"]

    async def _record_pipeline(
        self, thread_id: str, turn_id: str, stage: str, details: dict[str, Any] | None = None
    ) -> None:
        labels = {
            "setup": "Setup", "pre_start": "Pre-Start", "post_start": "Post-Start",
            "input_received": "Input Received", "input_cached": "Input Cached",
            "input_routed": "Input Routed", "input_compressed": "Input Compressed",
            "input_remembered": "Input Remembered",
            "pre_send": "Pre-Send", "post_send": "Post-Send",
            "response_received": "Response Received",
        }
        event: dict[str, Any] = {
            "kind": "pipeline_stage",
            "threadId": thread_id,
            "turnId": turn_id,
            "stage": stage,
            "label": labels.get(stage, stage),
        }
        if details:
            event["details"] = details
        await self._opts.events.record(event)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _is_parallel_safe(call: ToolCallLike, approval_policy: str) -> bool:
    if call.tool_name not in PARALLEL_READ_ONLY_TOOL_NAMES:
        return False
    if approval_policy in ("untrusted", "never"):
        return False
    return True


def _new_id_suffix() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
