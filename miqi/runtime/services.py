"""Shared runtime services — builds and owns the service graph for one session.

This is the single factory that creates AgentLoop, ToolOrchestrator,
AgentControl, and all related wiring. Frontends should use RuntimeSession
instead of building AgentLoop directly.

All heavy imports are lazy to avoid circular imports with AgentLoop
(which imports from miqi.runtime for TurnContext/AgentRegistry).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RuntimeEventEmitter:
    """Event emitter that routes typed protocol events to a configurable sink."""

    def __init__(self, sink: Any | None = None):
        self._sink = sink

    async def emit(self, event: Any) -> None:
        if self._sink is None:
            return
        await self._sink(event)


@dataclass
class RuntimeServices:
    """All services needed for a single runtime session.

    Owns AgentLoop, ToolOrchestrator, AgentControl, event emitter, and
    the shared tool registry. Created once per session via from_config().
    """

    session_id: str
    workspace: Path
    bus: Any  # MessageBus
    provider: Any
    event_emitter: RuntimeEventEmitter
    agent_loop: Any  # AgentLoop
    tool_registry: Any
    orchestrator: Any
    agent_registry: Any  # AgentRegistry
    agent_control: Any  # AgentControl
    tool_runtime: Any  # ToolRuntime (Phase 12)
    context_runtime: Any  # ContextRuntime (Phase 12)
    turn_runner: Any  # TurnRunner (Phase 12)
    # Phase 13
    plugin_manager: Any | None = None
    agent_jobs: Any | None = None  # AgentJobRuntime
    capability_resolver: Any | None = None  # CapabilityResolver

    @classmethod
    def from_config(
        cls,
        *,
        config: Any,
        provider: Any,
        session_id: str,
        workspace: Path,
        event_sink: Any | None = None,
    ) -> "RuntimeServices":
        """Build the full service graph from a Config + provider.

        Returns a RuntimeServices ready for use by RuntimeSession.
        """
        # Lazy imports to avoid circular imports with AgentLoop
        from miqi.agent.loop import AgentLoop
        from miqi.bus.queue import MessageBus
        from miqi.execution.factory import create_default_orchestrator
        from miqi.runtime.agent_control import AgentControl
        from miqi.runtime.agent_registry import AgentRegistry

        bus = MessageBus()
        defaults = config.agents.defaults
        agent_loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace,
            agent_name=defaults.name,
            model=defaults.model,
            temperature=defaults.temperature,
            max_tokens=defaults.max_tokens,
            max_iterations=defaults.max_tool_iterations,
            reflect_after_tool_calls=defaults.reflect_after_tool_calls,
            web_config=config.tools.web,
            paper_config=config.tools.papers,
            memory_window=defaults.memory_window,
            max_tool_result_chars=defaults.max_tool_result_chars,
            context_limit_chars=defaults.context_limit_chars,
            exec_config=config.tools.exec,
            memory_config=config.agents.memory,
            self_improvement_config=config.agents.self_improvement,
            session_config=config.agents.sessions,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            mcp_servers=config.tools.mcp_servers,
            channels_config=config.channels,
        )

        emitter = RuntimeEventEmitter(event_sink)

        orchestrator = create_default_orchestrator(
            tool_registry=agent_loop.tools,
            event_emitter=emitter,
        )
        agent_loop.set_orchestrator(orchestrator)

        registry = AgentRegistry()
        agent_control = AgentControl(
            session_id=session_id,
            registry=registry,
            event_emitter=emitter,
            workspace=workspace,
            provider=provider,
            orchestrator=orchestrator,
            tool_registry=agent_loop.tools,
        )

        # Wire SpawnTool into AgentControl
        spawn_tool = agent_loop.tools.get("spawn")
        if spawn_tool is not None and hasattr(spawn_tool, "_agent_control"):
            spawn_tool._agent_control = agent_control
            spawn_tool._event_emitter = emitter

        # Phase 12: runtime-owned turn execution components
        from miqi.runtime.context_runtime import ContextRuntime
        from miqi.runtime.tool_runtime import ToolRuntime
        from miqi.runtime.turn_runner import TurnRunner

        tool_runtime = ToolRuntime(orchestrator=orchestrator)
        context_runtime = ContextRuntime()

        # Phase 13: capability resolver (requires PluginManager and ToolRegistry)
        from pathlib import Path as _Path
        from miqi.runtime.capabilities import CapabilityResolver
        from miqi.skills.plugin_manager import PluginManager

        plugin_manager = PluginManager(
            user_plugins_dir=_Path.home() / ".miqi" / "plugins",
            system_plugins_dir=_Path(__file__).parent.parent / "plugins",
            workspace=workspace,
        )

        capability_resolver = CapabilityResolver(
            tool_registry=agent_loop.tools,
            plugin_manager=plugin_manager,
        )

        turn_runner = TurnRunner(
            provider=provider,
            tool_runtime=tool_runtime,
            context_runtime=context_runtime,
            event_emitter=emitter,
            max_iterations=defaults.max_tool_iterations,
            capability_resolver=capability_resolver,
        )

        # Phase 13: AgentJobRuntime (depends on TurnRunner)
        from miqi.runtime.agent_jobs import AgentJobRuntime

        # Build partial services so AgentJobRuntime can reference them
        services = cls(
            session_id=session_id,
            workspace=workspace,
            bus=bus,
            provider=provider,
            event_emitter=emitter,
            agent_loop=agent_loop,
            tool_registry=agent_loop.tools,
            orchestrator=orchestrator,
            agent_registry=registry,
            agent_control=agent_control,
            tool_runtime=tool_runtime,
            context_runtime=context_runtime,
            turn_runner=turn_runner,
            plugin_manager=plugin_manager,
            capability_resolver=capability_resolver,
        )

        agent_jobs = AgentJobRuntime(services=services)
        services.agent_jobs = agent_jobs

        # Wire AgentJobRuntime into AgentControl (Phase 13 delegation)
        agent_control._agent_jobs = agent_jobs

        return services
