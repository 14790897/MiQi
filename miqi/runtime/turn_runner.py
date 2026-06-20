"""Turn runner — the runtime-owned provider.chat + tool loop.

Historical: Extracted from the legacy AgentLoop._run_agent_loop. Executes a
single turn: calls the provider, routes tool calls through ToolRuntime,
builds messages through ContextRuntime, and returns TurnResult.

Also provides run_agent_job() for AgentJobRuntime — a simplified
single-turn execution path for sub-agent jobs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnResult:
    """Result of a completed turn."""
    final_content: str
    messages: list[dict[str, Any]]
    tools_used: list[str]
    token_usage: dict[str, int] = field(default_factory=dict)
    messages_delta: list[dict[str, Any]] = field(default_factory=list)


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
    ):
        self._provider = provider
        self._tools = tool_runtime
        self._context = context_runtime
        self._events = event_emitter
        self._max_iterations = max_iterations
        self._capability_resolver = capability_resolver
        self._ledger = ledger_runtime

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
    ) -> TurnResult:
        """Execute a full turn: model calls until final response or max iters.

        Phase 14 follow-up: checks cancel_event (asyncio.Event) at each
        iteration and yields with CancelledError when set.
        Phase 41: drains steer_queue at safe boundaries and continues
        the same turn instead of completing immediately.
        """
        messages = self._context.build_initial_messages(
            turn=turn,
            user_content=user_content,
            system_prompt=system_prompt,
            history=history,
        )
        tools_used: list[str] = []
        # Phase 17: accumulate messages added during this turn for persistence.
        # Each entry is a provider-compatible {role, content, ...} dict.
        messages_delta: list[dict[str, Any]] = []

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

        for _iteration in range(self._max_iterations):
            # Phase 14 follow-up: check cancellation before expensive work
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError("Turn cancelled via AbortTurn")

            # Phase 20: prefer streaming. stream_chat() is a base-class
            # method on LLMProvider so every provider supports it — the
            # default wraps chat() and yields a single "completed" event.
            response: Any = None
            content_parts: list[str] = []
            async for stream_event in self._provider.stream_chat(
                messages=messages,
                tools=tools,
                model=turn.model,
                temperature=turn.temperature,
                max_tokens=turn.max_tokens,
            ):
                if stream_event.kind == "content_delta":
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
                    from miqi.protocol.events import AgentReasoningEvent
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

            if not response.has_tool_calls:
                # Phase 41: drain steering messages before completing
                steers = await _drain_steer_messages()
                if steers:
                    for steer in steers:
                        content = steer["content"]
                        messages.append({"role": "user", "content": content})
                        delta: dict[str, Any] = {
                            "role": "user",
                            "content": content,
                        }
                        cid = steer.get("client_user_message_id")
                        if cid is not None:
                            delta["client_user_message_id"] = cid
                        if steer.get("input_items"):
                            delta["input_items"] = steer["input_items"]
                        messages_delta.append(delta)
                    continue

                content = response.content or ""
                messages = self._context.add_assistant_message(
                    messages=messages,
                    content=content,
                )
                # Append final assistant message to delta
                messages_delta.append({"role": "assistant", "content": content})
                return TurnResult(
                    final_content=content,
                    messages=messages,
                    tools_used=tools_used,
                    token_usage=getattr(response, "usage", {}) or {},
                    messages_delta=messages_delta,
                )

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

            # Execute tool calls concurrently through ToolRuntime
            contexts = await self._tools.execute_many(turn, response.tool_calls)

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
                            else "{}"
                        ),
                    },
                })

            # 2. Assistant message with tool_calls MUST precede tool results
            messages = self._context.add_assistant_message(
                messages=messages,
                content=response.content or "",
                tool_calls=assistant_tool_calls,
            )
            # Persist assistant(tool_calls) in messages_delta
            asst_delta: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or None,
                "tool_calls": assistant_tool_calls,
            }
            messages_delta.append(asst_delta)

            # 3. Append tool results in order (assistant → tool → tool → …)
            for tool_call, ctx in zip(response.tool_calls, contexts):
                messages = self._context.add_tool_result(
                    messages=messages,
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    content=ctx.result or "",
                )
                # Persist tool result in messages_delta
                messages_delta.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": ctx.result or "",
                })

        # Exhausted iterations
        content = (
            f"Reached maximum iterations ({self._max_iterations}). "
            f"Tools used: {', '.join(dict.fromkeys(tools_used)) or 'none'}. "
            f"Try breaking your task into smaller steps."
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
            model="default",
            provider=self._provider,
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

        return await self.run(
            turn=turn,
            user_content=job.task,
            system_prompt=metadata.system_prompt,
            tools=tools,
        )
