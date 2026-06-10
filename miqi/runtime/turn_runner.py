"""Turn runner — the runtime-owned provider.chat + tool loop.

Extracted from AgentLoop._run_agent_loop. Executes a single turn:
calls the provider, routes tool calls through ToolRuntime, builds
messages through ContextRuntime, and returns TurnResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TurnResult:
    """Result of a completed turn."""
    final_content: str
    messages: list[dict[str, Any]]
    tools_used: list[str]


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
    ):
        self._provider = provider
        self._tools = tool_runtime
        self._context = context_runtime
        self._events = event_emitter
        self._max_iterations = max_iterations

    async def run(
        self,
        *,
        turn: Any,
        user_content: str,
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
        history: list[dict[str, Any]] | None = None,
    ) -> TurnResult:
        """Execute a full turn: model calls until final response or max iters."""
        messages = self._context.build_initial_messages(
            turn=turn,
            user_content=user_content,
            system_prompt=system_prompt,
            history=history,
        )
        tools_used: list[str] = []

        for _iteration in range(self._max_iterations):
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
                return TurnResult(content, messages, tools_used)

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

            # 3. Append tool results in order (assistant → tool → tool → …)
            for tool_call, ctx in zip(response.tool_calls, contexts):
                messages = self._context.add_tool_result(
                    messages=messages,
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    content=ctx.result or "",
                )

        # Exhausted iterations
        return TurnResult(
            final_content=(
                f"Reached maximum iterations ({self._max_iterations}). "
                f"Tools used: {', '.join(dict.fromkeys(tools_used)) or 'none'}. "
                f"Try breaking your task into smaller steps."
            ),
            messages=messages,
            tools_used=tools_used,
        )
