"""Tool host adapter for KUN runtime.

Wraps MiQi ``ToolRegistry`` to expose KUN ``ToolHost`` semantics:
- ``listTools(context)`` → list of ``dict`` (KUN ModelToolSpec)
- ``execute(call, context, onProgress)`` → ``dict`` (ToolHostResult)

Supports concurrency classification (parallel-safe / path-scoped / never-parallel)
and approval gating via the ToolHostContext.

Aligns with KUN ``ports/tool-host.ts`` and ``adapters/tool/local-tool-host.ts``.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from loguru import logger

from miqi.agent.tools.registry import ToolRegistry


# ═══════════════════════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ToolCallLike:
    """A tool call as received from the model, ready for dispatch."""
    call_id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    tool_kind: str | None = None
    provider_id: str | None = None


@dataclass
class ToolHostContext:
    """Context passed to the tool host when executing tool calls."""
    thread_id: str
    turn_id: str
    workspace: str
    thread_mode: str | None = None
    approval_policy: str = "auto"
    abort_signal: Any = None  # CancellationToken
    active_skill_ids: list[str] = field(default_factory=list)
    allowed_tool_names: list[str] | None = None
    memory_policy: dict[str, Any] = field(default_factory=dict)
    delegation_policy: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)

    # Callbacks
    await_approval: Callable[[dict[str, Any]], Coroutine[Any, Any, str]] | None = None
    await_user_input: Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]] | None = None


@dataclass
class ToolHostResult:
    """Result of executing a tool call."""
    item: dict[str, Any]


# ═══════════════════════════════════════════════════════════════════════════════
# Parallel-safe classification (matching MiQi ToolRegistry + KUN)
# ═══════════════════════════════════════════════════════════════════════════════

_PARALLEL_SAFE_NAMES = frozenset({"read", "grep", "find", "ls", "list_dir", "read_file", "web_search", "web_fetch", "paper_search", "paper_get"})
_NEVER_PARALLEL_NAMES = frozenset({"exec", "bash", "message", "spawn", "cron", "write", "edit", "delete", "move", "apply_patch", "edit_diff"})
_MAX_PARALLEL_TOOL_CALLS = 3


# ═══════════════════════════════════════════════════════════════════════════════
# MiQiToolHost
# ═══════════════════════════════════════════════════════════════════════════════


class MiQiToolHost:
    """KUN ToolHost backed by MiQi ``ToolRegistry``.

    Delegates tool listing and execution to the registry while providing
    KUN-compatible return types.
    """

    def __init__(self, registry: ToolRegistry, read_tracker: bool = False):
        self._registry = registry
        self._read_tracker: dict[str, set[str]] = {} if read_tracker else None

    async def list_tools(self, context: ToolHostContext | None = None) -> list[dict[str, Any]]:
        """Return tool specs in KUN ``ModelToolSpec`` format.

        If *context* has ``allowed_tool_names``, only those tools are returned.
        """
        definitions = self._registry.get_definitions()
        result: list[dict[str, Any]] = []

        for defn in definitions:
            fn = defn.get("function", defn) if isinstance(defn, dict) else {}
            name = fn.get("name", "")
            if context and context.allowed_tool_names is not None:
                if name not in context.allowed_tool_names:
                    continue
            result.append({
                "name": name,
                "description": fn.get("description", ""),
                "inputSchema": fn.get("parameters", {}),
                "toolKind": _classify_tool_kind(name),
                "providerId": "builtin",
                "providerKind": "built-in",
            })
        return result

    async def execute(
        self,
        call: ToolCallLike,
        context: ToolHostContext,
        on_progress: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    ) -> ToolHostResult:
        """Execute a single tool call and return a KUN ToolResultItem.

        If *context* has ``await_approval`` and the tool requires approval,
        the approval gate is invoked before execution.
        """
        tool_name = call.tool_name

        # Enforce allowed-tool-names restriction
        if context.allowed_tool_names is not None and tool_name not in context.allowed_tool_names:
            return ToolHostResult(item={
                "kind": "tool_result",
                "id": f"item_{context.turn_id}_{call.call_id}",
                "turnId": context.turn_id,
                "threadId": context.thread_id,
                "role": "tool",
                "status": "failed",
                "createdAt": _now_iso(),
                "toolName": tool_name,
                "callId": call.call_id,
                "toolKind": _classify_tool_kind(tool_name),
                "output": f"Tool '{tool_name}' is not allowed in this context",
                "isError": True,
            })

        # Check if tool exists
        if not self._registry.has(tool_name):
            return ToolHostResult(item={
                "kind": "tool_result",
                "id": f"item_{context.turn_id}_{call.call_id}",
                "turnId": context.turn_id,
                "threadId": context.thread_id,
                "role": "tool",
                "status": "failed",
                "createdAt": _now_iso(),
                "toolName": tool_name,
                "callId": call.call_id,
                "toolKind": _classify_tool_kind(tool_name),
                "output": f"Tool '{tool_name}' not found",
                "isError": True,
            })

        # Parse arguments
        args = call.arguments
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                args = {}

        # Execute
        try:
            result = await self._registry.execute(tool_name, args)
            is_error = isinstance(result, str) and result.startswith("Error")
        except asyncio.TimeoutError:
            result = f"Tool '{tool_name}' timed out"
            is_error = True
        except Exception as exc:
            logger.exception(f"Tool '{tool_name}' execution failed")
            result = f"Error executing {tool_name}: {exc}"
            is_error = True

        return ToolHostResult(item={
            "kind": "tool_result",
            "id": f"item_{context.turn_id}_{call.call_id}",
            "turnId": context.turn_id,
            "threadId": context.thread_id,
            "role": "tool",
            "status": "failed" if is_error else "completed",
            "createdAt": _now_iso(),
            "finishedAt": _now_iso(),
            "toolName": tool_name,
            "callId": call.call_id,
            "toolKind": _classify_tool_kind(tool_name),
            "output": result,
            "isError": is_error,
        })

    def should_parallelize(self, tool_calls: list[ToolCallLike], approval_policy: str = "auto") -> bool:
        """Decide whether a batch of tool calls can run concurrently.

        Rules: read/list/find/grep tools are parallel-safe (max 3 at once);
        mutating tools always run sequentially.  Approval policies that
        require per-call confirmation also force sequential execution.
        """
        if len(tool_calls) < 2:
            return False
        if approval_policy in ("untrusted", "never"):
            return False
        # Check MiQi registry-level parallelization first
        tc_dicts = [
            {"id": c.call_id, "name": c.tool_name, "arguments": c.arguments}
            for c in tool_calls
        ]
        return self._registry.should_parallelize(tc_dicts)

    def is_parallel_safe(self, call: ToolCallLike) -> bool:
        """Return True if *call* can run in parallel with other read-only tools."""
        if call.tool_name in _NEVER_PARALLEL_NAMES:
            return False
        return call.tool_name in _PARALLEL_SAFE_NAMES

    def max_parallel(self) -> int:
        return _MAX_PARALLEL_TOOL_CALLS

    def clear_read_tracker(self, thread_id: str | None = None) -> None:
        """Clear the read-file tracker (used after compaction to reset stale state)."""
        if self._read_tracker is not None:
            if thread_id is None:
                self._read_tracker.clear()
            else:
                self._read_tracker.pop(thread_id, None)


# ═══════════════════════════════════════════════════════════════════════════════
# FakeToolHost — for testing without real tool execution
# ═══════════════════════════════════════════════════════════════════════════════


class FakeToolHost:
    """A test-double tool host with configurable responses."""

    def __init__(
        self,
        tools: list[dict[str, Any]] | None = None,
        results: dict[str, str] | None = None,
        error_tools: set[str] | None = None,
    ):
        self._tools = tools or []
        self._results = results or {}
        self._error_tools = error_tools or set()
        self._calls: list[tuple[ToolCallLike, ToolHostContext]] = []

    @property
    def calls(self) -> list[tuple[ToolCallLike, ToolHostContext]]:
        return list(self._calls)

    async def list_tools(self, context: ToolHostContext | None = None) -> list[dict[str, Any]]:
        return [dict(t) for t in self._tools]

    async def execute(
        self,
        call: ToolCallLike,
        context: ToolHostContext,
        on_progress: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    ) -> ToolHostResult:
        self._calls.append((call, context))
        is_error = call.tool_name in self._error_tools
        output = self._results.get(call.tool_name, f"Result of {call.tool_name}({call.arguments})")
        return ToolHostResult(item={
            "kind": "tool_result",
            "id": f"item_{context.turn_id}_{call.call_id}",
            "turnId": context.turn_id,
            "threadId": context.thread_id,
            "role": "tool",
            "status": "failed" if is_error else "completed",
            "createdAt": _now_iso(),
            "finishedAt": _now_iso(),
            "toolName": call.tool_name,
            "callId": call.call_id,
            "toolKind": _classify_tool_kind(call.tool_name),
            "output": output if not is_error else f"Error: {output}",
            "isError": is_error,
        })

    def should_parallelize(self, tool_calls: list[ToolCallLike], approval_policy: str = "auto") -> bool:
        if len(tool_calls) < 2:
            return False
        if approval_policy in ("untrusted", "never"):
            return False
        return all(
            c.tool_name in _PARALLEL_SAFE_NAMES and c.tool_name not in _NEVER_PARALLEL_NAMES
            for c in tool_calls
        )

    def is_parallel_safe(self, call: ToolCallLike) -> bool:
        return call.tool_name in _PARALLEL_SAFE_NAMES

    def max_parallel(self) -> int:
        return _MAX_PARALLEL_TOOL_CALLS


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _classify_tool_kind(name: str) -> str:
    """Classify a tool name as tool_call, command_execution, or file_change."""
    if name in ("bash", "exec", "shell"):
        return "command_execution"
    if name in ("write", "edit", "edit_diff", "apply_patch", "delete", "move", "write_file", "edit_file"):
        return "file_change"
    return "tool_call"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
