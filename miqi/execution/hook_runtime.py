"""Hook runtime — pre/post tool-use hooks.

Hooks are Python callables registered against tool patterns.
They run synchronously in the tool execution context.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Awaitable

from loguru import logger


class HookPoint(str, Enum):
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"


HookCallback = Callable[[Any], Awaitable[None]]


@dataclass
class HookRegistration:
    hook_point: HookPoint
    tool_pattern: str  # fnmatch pattern, e.g. "exec", "write_*", "*"
    callback: HookCallback
    priority: int = 100  # lower = runs first


class HookRuntime:
    """Manages and executes hooks."""

    def __init__(self):
        self._hooks: dict[HookPoint, list[HookRegistration]] = {
            p: [] for p in HookPoint
        }

    def register(self, reg: HookRegistration) -> None:
        self._hooks[reg.hook_point].append(reg)
        self._hooks[reg.hook_point].sort(key=lambda h: h.priority)
        logger.debug(
            "Registered hook: {} → {} (priority={})",
            reg.hook_point.value, reg.tool_pattern, reg.priority,
        )

    async def run(self, point: HookPoint, ctx: Any) -> None:
        """Run all hooks registered for this point that match the tool."""
        for reg in self._hooks.get(point, []):
            if fnmatch.fnmatch(ctx.tool_name, reg.tool_pattern):
                try:
                    await reg.callback(ctx)
                except Exception:
                    logger.exception(
                        "Hook {} failed for {}", reg.tool_pattern, ctx.tool_name
                    )
