"""KUN runtime composition root — wires all components together.

Aligns with KUN ``server/runtime-factory.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from miqi.kun_runtime.auth import BearerTokenAuth
from miqi.kun_runtime.cancellation import InflightTracker
from miqi.kun_runtime.compactor import ContextCompactor
from miqi.kun_runtime.event_bus import EventBus
from miqi.kun_runtime.event_recorder import RuntimeEventRecorder
from miqi.kun_runtime.loop import AgentLoop, AgentLoopOptions
from miqi.kun_runtime.model_client import MiQiModelClient
from miqi.kun_runtime.stores import FileSessionStore, FileThreadStore
from miqi.kun_runtime.thread_service import ThreadService
from miqi.kun_runtime.tool_host import MiQiToolHost
from miqi.kun_runtime.turn_service import TurnService
from miqi.kun_runtime.usage import UsageService


@dataclass
class RuntimeOptions:
    """Configuration for the KUN runtime."""

    data_dir: str | Path
    workspace: str
    model: str
    runtime_token: str = "insecure-dev-token"
    insecure: bool = True
    host: str = "127.0.0.1"
    port: int = 9876
    token_economy_enabled: bool = False
    approval_policy: str = "auto"


class KunRuntime:
    """Composition root that wires all KUN runtime components.

    Usage::

        runtime = KunRuntime(RuntimeOptions(data_dir="./data", workspace="./ws", model="deepseek-chat"))
        await runtime.start()
        thread = await runtime.threads.create(workspace="./ws", model="deepseek-chat")
        result = await runtime.turns.start_turn(thread["id"], "Hello!")
        await runtime.loop.run_turn(thread["id"], result["turnId"])
    """

    def __init__(self, options: RuntimeOptions):
        self._options = options
        data_dir = Path(options.data_dir)

        # Transports
        self.event_bus = EventBus()

        # Stores
        self.thread_store = FileThreadStore(data_dir)
        self.session_store = FileSessionStore(data_dir)

        # Auth
        self.auth = BearerTokenAuth(token=options.runtime_token, insecure=options.insecure)

        # Services
        self.usage = UsageService()
        self.inflight = InflightTracker()
        self.events = RuntimeEventRecorder(self.event_bus)

        # Turn/Thread services
        self.turns = TurnService(self.thread_store, self.session_store, self.events, self.inflight)
        self.threads = ThreadService(self.thread_store, self.session_store, self.events)

        # Compactor
        self.compactor = ContextCompactor()

        # Model client — set later via set_provider()
        self.model: Any = None  # MiQiModelClient | FakeModelClient

        # Tool host — set later via set_tool_registry()
        self.tool_host: Any = None  # MiQiToolHost | FakeToolHost

        # Gates
        self.approval_gate: Any = None  # set later
        self.user_input_gate: Any = None  # set later

        # Loop (created lazily)
        self._loop: AgentLoop | None = None

    def set_provider(self, provider: Any) -> None:
        """Wire the MiQi LLMProvider into the model client."""
        self.model = MiQiModelClient(provider)

    def set_tool_registry(self, registry: Any) -> None:
        """Wire the MiQi ToolRegistry into the tool host."""
        self.tool_host = MiQiToolHost(registry)

    @property
    def loop(self) -> AgentLoop:
        """Return the configured agent loop."""
        if self._loop is None:
            if self.model is None:
                raise RuntimeError("Model client not configured — call set_provider() first")
            if self.tool_host is None:
                raise RuntimeError("Tool host not configured — call set_tool_registry() first")

            self._loop = AgentLoop(AgentLoopOptions(
                thread_store=self.thread_store,
                session_store=self.session_store,
                model=self.model,
                tool_host=self.tool_host,
                usage=self.usage,
                events=self.events,
                turns=self.turns,
                inflight=self.inflight,
                compactor=self.compactor,
                approval_gate=self.approval_gate,
                user_input_gate=self.user_input_gate,
            ))
        return self._loop

    async def run_turn(self, thread_id: str, turn_id: str) -> str:
        """Convenience: run a turn on the configured loop."""
        return await self.loop.run_turn(thread_id, turn_id)

    def info(self) -> dict[str, Any]:
        """Return runtime info for health checks."""
        return {
            "host": self._options.host,
            "port": self._options.port,
            "model": self._options.model,
            "workspace": self._options.workspace,
            "dataDir": str(self._options.data_dir),
            "insecure": self._options.insecure,
        }
