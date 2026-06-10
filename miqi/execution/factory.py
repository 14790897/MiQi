"""Shared orchestrator factory — avoids duplicating ToolOrchestrator setup.

Used by CLI agent/gateway/cron, TUI, bridge, and any other entry point
that creates an AgentLoop and needs a configured orchestrator.
"""

from __future__ import annotations

from typing import Any


class NoopEmitter:
    """Event emitter that silently discards all events."""

    async def emit(self, event: Any) -> None:
        pass


def create_default_orchestrator(
    tool_registry: Any,
    event_emitter: Any | None = None,
    *,
    bwrap_available: bool = False,
    permanent_allowlist: set[str] | None = None,
) -> Any:
    """Create a ToolOrchestrator with sensible defaults.

    Args:
        tool_registry: ToolRegistry instance (or None, wired later).
        event_emitter: EventEmitter for typed events. Uses NoopEmitter if None.
        bwrap_available: Whether bwrap sandboxing is available on this system.
        permanent_allowlist: Set of commands that bypass permission checks.

    Returns:
        Configured ToolOrchestrator instance.
    """
    from miqi.execution.orchestrator import ToolOrchestrator
    from miqi.execution.permission_engine import PermissionEngine
    from miqi.execution.sandbox_policy import SandboxPolicyEngine
    from miqi.execution.hook_runtime import HookRuntime

    emitter = event_emitter if event_emitter is not None else NoopEmitter()

    return ToolOrchestrator(
        permission_engine=PermissionEngine(
            permanent_allowlist=permanent_allowlist or set(),
        ),
        sandbox_engine=SandboxPolicyEngine(bwrap_available=bwrap_available),
        hook_runtime=HookRuntime(),
        tool_registry=tool_registry,
        event_emitter=emitter,
    )


def configure_agent_orchestrator(
    agent_loop: Any,
    event_emitter: Any | None = None,
    *,
    bwrap_available: bool = False,
) -> None:
    """Create and wire a default orchestrator onto an AgentLoop.

    After this call, agent_loop._orchestrator is guaranteed non-None
    and agent_loop._orchestrator.tools == agent_loop.tools.

    Args:
        agent_loop: AgentLoop instance (after construction, before first turn).
        event_emitter: EventEmitter or None (NoopEmitter used when None).
        bwrap_available: Whether bwrap sandboxing is available.
    """
    orchestrator = create_default_orchestrator(
        tool_registry=None,  # Will be set below
        event_emitter=event_emitter,
        bwrap_available=bwrap_available,
    )
    orchestrator.tools = agent_loop.tools
    agent_loop.set_orchestrator(orchestrator)
