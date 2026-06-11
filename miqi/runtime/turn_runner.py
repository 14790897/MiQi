"""Turn runner — the runtime-owned provider.chat + tool loop.

Extracted from AgentLoop._run_agent_loop. Executes a single turn:
calls the provider, routes tool calls through ToolRuntime, builds
messages through ContextRuntime, and returns TurnResult.

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
    ):
        self._provider = provider
        self._tools = tool_runtime
        self._context = context_runtime
        self._events = event_emitter
        self._max_iterations = max_iterations
        self._capability_resolver = capability_resolver

    async def run(
        self,
        *,
        turn: Any,
        user_content: str,
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
        history: list[dict[str, Any]] | None = None,
        cancel_event: Any | None = None,
    ) -> TurnResult:
        """Execute a full turn: model calls until final response or max iters.

        Phase 14 follow-up: checks cancel_event (asyncio.Event) at each
        iteration and yields with CancelledError when set.
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

        for _iteration in range(self._max_iterations):
            # Phase 14 follow-up: check cancellation before expensive work
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError("Turn cancelled via AbortTurn")

            response = await self._provider.chat(
                messages=messages,
                tools=tools,
                model=turn.model,
                temperature=turn.temperature,
                max_tokens=turn.max_tokens,
            )

            if not response.has_tool_calls:
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

            # Execute tool calls concurrently through ToolRuntime
            contexts = await self._tools.execute_many(turn, response.tool_calls)

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
