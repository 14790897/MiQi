"""Shared runtime services — builds and owns the service graph for one session.

This is the single factory that creates the full service graph (ToolRegistry,
ToolOrchestrator, AgentControl, TurnRunner, PluginManager, CapabilityResolver,
McpRuntime, etc.) for one session. Frontends should use RuntimeSession instead
of building services directly.

Phase 48: RuntimeServices owns the service graph directly. Model configuration
is carried by the immutable RuntimeModelSettings value object.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from miqi.execution.hook_runtime import HookRuntime


class RuntimeEventEmitter:
    """Event emitter that routes typed protocol events to a configurable sink."""

    def __init__(self, sink: Any | None = None):
        self._sink = sink

    async def emit(self, event: Any) -> None:
        if self._sink is None:
            return
        await self._sink(event)


@dataclass(frozen=True)
class RuntimeModelSettings:
    """Model configuration consumed by runtime-owned execution."""

    model: str
    temperature: float
    max_tokens: int
    max_tool_result_chars: int
    context_limit_chars: int


@dataclass
class RuntimeServices:
    """All services needed for a single runtime session.

    Owns the full service graph for a single session — ToolRegistry,
    ToolOrchestrator, AgentControl, TurnRunner, PluginManager,
    CapabilityResolver, McpRuntime, and all related wiring.
    Created once per session via from_config().
    """

    session_id: str
    workspace: Path
    bus: Any  # MessageBus
    provider: Any
    event_emitter: RuntimeEventEmitter
    model_settings: RuntimeModelSettings  # immutable model config from config.agents.defaults
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
    # Phase 17: session / thread / history runtime
    session_state: Any | None = None
    history_runtime: Any | None = None
    thread_runtime: Any | None = None
    # Phase 21: MCP runtime adapter
    mcp_runtime: Any | None = None
    # Phase 24: append-only event ledger
    ledger_runtime: Any | None = None
    # Phase 25: replay/debug runtime
    replay_runtime: Any | None = None
    # Phase 51.3: shared lifecycle hook runtime
    hooks: HookRuntime | None = None
    # Phase 52: shared agent graph persistence
    agent_graph_store: Any | None = None

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
        # Lazy imports to avoid circular imports
        from miqi.bus.queue import MessageBus
        from miqi.execution.factory import create_default_orchestrator
        from miqi.plan.plan_tracker import PlanTracker
        from miqi.runtime.agent_control import AgentControl
        from miqi.runtime.agent_registry import AgentRegistry
        from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

        bus = MessageBus()
        defaults = config.agents.defaults

        # Historical (Phase 22): runtime-owned tool registry (replaced AgentLoop._register_default_tools)
        plan_tracker = PlanTracker()
        tool_registry = create_runtime_tool_registry(
            config=config,
            workspace=workspace,
            provider=provider,
            bus=bus,
            approval_callback=None,
            sandbox_manager=None,
            plan_tracker=plan_tracker,
        )

        # Immutable model configuration for runtime-owned execution
        model_settings = RuntimeModelSettings(
            model=defaults.model,
            temperature=defaults.temperature,
            max_tokens=defaults.max_tokens,
            max_tool_result_chars=defaults.max_tool_result_chars,
            context_limit_chars=defaults.context_limit_chars,
        )

        emitter = RuntimeEventEmitter(event_sink)
        hook_runtime = HookRuntime()

        orchestrator = create_default_orchestrator(
            tool_registry=tool_registry,
            event_emitter=emitter,
        )

        # Phase 52: shared agent graph persistence (created before AgentControl)
        agent_graph_db = workspace / ".miqi-runtime" / "agent_graph.db"
        from miqi.runtime.agent_graph_store import AgentGraphStore

        agent_graph_store = AgentGraphStore(agent_graph_db)

        registry = AgentRegistry()
        agent_control = AgentControl(
            session_id=session_id,
            registry=registry,
            event_emitter=emitter,
            workspace=workspace,
            provider=provider,
            orchestrator=orchestrator,
            tool_registry=tool_registry,
            hooks=hook_runtime,
            store=agent_graph_store,
        )

        # Wire SpawnTool into AgentControl
        spawn_tool = tool_registry.get("spawn")
        if spawn_tool is not None and hasattr(spawn_tool, "_agent_control"):
            spawn_tool._agent_control = agent_control
            spawn_tool._event_emitter = emitter

        # Phase 12: runtime-owned turn execution components
        from miqi.runtime.context_runtime import ContextRuntime
        from miqi.runtime.tool_runtime import ToolRuntime
        from miqi.runtime.turn_runner import TurnRunner

        tool_runtime = ToolRuntime(orchestrator=orchestrator)

        # Phase 19 follow-up: wire real ContextCompressor via provider.chat()
        async def _summarize_for_compaction(
            msgs: list[dict[str, Any]], model: str,
        ) -> str:
            response = await provider.chat(
                messages=msgs,
                tools=None,
                model=model,
                temperature=0.3,
                max_tokens=4096,
            )
            return response.content or ""

        context_runtime = ContextRuntime(
            llm_call_fn=_summarize_for_compaction,
            context_limit_chars=defaults.context_limit_chars,
            hooks=hook_runtime,
        )

        # Phase 13: capability resolver (requires PluginManager and ToolRegistry)
        from pathlib import Path as _Path
        from miqi.runtime.capabilities import CapabilityResolver
        from miqi.skills.plugin_manager import PluginManager

        plugin_manager = PluginManager(
            user_plugins_dir=_Path.home() / ".miqi" / "plugins",
            system_plugins_dir=_Path(__file__).parent.parent / "plugins",
            workspace=workspace,
            hook_runtime=hook_runtime,
        )

        capability_resolver = CapabilityResolver(
            tool_registry=tool_registry,
            plugin_manager=plugin_manager,
        )

        # Phase 21: MCP runtime adapter
        from miqi.runtime.mcp_runtime import McpRuntime
        mcp_runtime = McpRuntime(plugin_manager=plugin_manager)

        # Phase 24: ledger runtime (created early so TurnRunner can use it)
        runtime_db = workspace / ".miqi-runtime" / "runtime.db"
        from miqi.runtime.ledger_runtime import LedgerRuntime

        ledger_runtime = LedgerRuntime(runtime_db, session_id=session_id)

        # Phase 31.8: wire ledger into orchestrator so exec/approval events
        # are recorded for replay.
        orchestrator._ledger = ledger_runtime

        # Phase 25: replay runtime (wraps ledger for reconstruction)
        from miqi.runtime.replay_runtime import ReplayRuntime

        replay_runtime = ReplayRuntime(ledger_runtime)

        turn_runner = TurnRunner(
            provider=provider,
            tool_runtime=tool_runtime,
            context_runtime=context_runtime,
            event_emitter=emitter,
            max_iterations=defaults.max_tool_iterations,
            capability_resolver=capability_resolver,
            ledger_runtime=ledger_runtime,
            hooks=hook_runtime,
        )

        # Phase 13: AgentJobRuntime (depends on TurnRunner)
        from miqi.runtime.agent_jobs import AgentJobRuntime

        # Phase 17: session state, history runtime, thread runtime
        from miqi.runtime.history_runtime import HistoryRuntime
        from miqi.runtime.session_state import SessionState
        from miqi.runtime.thread_runtime import ThreadRuntime

        history_runtime = HistoryRuntime(runtime_db, session_id=session_id)
        thread_runtime = ThreadRuntime(runtime_db, session_id=session_id)

        session_state = SessionState(
            session_id=session_id,
            workspace=workspace,
            active_thread_id=f"{session_id}:default",
            config_snapshot=config,
        )

        # Build partial services so AgentJobRuntime can reference them
        services = cls(
            session_id=session_id,
            workspace=workspace,
            bus=bus,
            provider=provider,
            event_emitter=emitter,
            model_settings=model_settings,
            tool_registry=tool_registry,
            orchestrator=orchestrator,
            agent_registry=registry,
            agent_control=agent_control,
            tool_runtime=tool_runtime,
            context_runtime=context_runtime,
            turn_runner=turn_runner,
            plugin_manager=plugin_manager,
            capability_resolver=capability_resolver,
            session_state=session_state,
            history_runtime=history_runtime,
            thread_runtime=thread_runtime,
            mcp_runtime=mcp_runtime,
            ledger_runtime=ledger_runtime,
            replay_runtime=replay_runtime,
            hooks=hook_runtime,
        )

        agent_jobs = AgentJobRuntime(services=services, store=agent_graph_store)
        services.agent_jobs = agent_jobs
        services.agent_graph_store = agent_graph_store

        # Wire AgentJobRuntime into AgentControl (Phase 13 delegation)
        agent_control._agent_jobs = agent_jobs

        return services
