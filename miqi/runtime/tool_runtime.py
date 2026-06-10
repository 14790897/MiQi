"""Tool runtime — the sole adapter for single and parallel tool execution.

All tool calls (single and concurrent batches) go through this adapter,
which creates ToolExecutionContext and routes through ToolOrchestrator.
No tool context construction is scattered across AgentLoop or other layers.
"""

from __future__ import annotations

import asyncio
from typing import Any

from miqi.execution.orchestrator import ToolExecutionContext


class ToolRuntime:
    """Unified tool execution adapter wrapping ToolOrchestrator."""

    def __init__(self, *, orchestrator: Any):
        if orchestrator is None:
            raise RuntimeError("ToolRuntime requires a ToolOrchestrator")
        self._orchestrator = orchestrator

    async def execute_one(self, turn: Any, tool_call: Any) -> ToolExecutionContext:
        """Execute a single tool call through the orchestrator."""
        ctx = ToolExecutionContext(
            tool_name=tool_call.name,
            tool_call_id=tool_call.id,
            arguments=tool_call.arguments,
            turn_id=turn.turn_id,
            thread_id=turn.thread_id,
            agent_type=turn.agent_metadata.name,
        )
        return await self._orchestrator.execute(ctx)

    async def execute_many(
        self, turn: Any, tool_calls: list[Any],
    ) -> list[ToolExecutionContext]:
        """Execute multiple tool calls concurrently through the orchestrator."""
        return await asyncio.gather(
            *[self.execute_one(turn, call) for call in tool_calls],
        )
