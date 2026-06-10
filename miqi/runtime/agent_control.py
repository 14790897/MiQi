"""Multi-agent control plane — spawn, fork, monitor, and communicate."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from miqi.protocol.events import (
    AgentStatus,
    SubAgentSpawnedEvent,
    SubAgentCompletedEvent,
    ErrorEvent,
    EventSeverity,
)
from miqi.runtime.agent_registry import AgentMetadata, AgentRegistry
from miqi.runtime.agent_status import AgentStateMachine


@dataclass
class LiveAgent:
    """A running agent instance."""
    agent_id: str
    thread_id: str
    metadata: AgentMetadata
    state: AgentStateMachine
    parent_agent_id: str | None = None
    spawned_at: float = field(default_factory=lambda: __import__("time").time())


class AgentControl:
    """Control plane for multi-agent operations.

    Each root session has one AgentControl instance shared with all
    sub-agents spawned from that root. This keeps the registry scoped
    to one session tree.
    """

    def __init__(
        self,
        session_id: str,
        registry: AgentRegistry,
        event_emitter: Any,  # EventEmitter — sends events to bridge
        workspace: Path,
    ):
        self.session_id = session_id
        self.registry = registry
        self._events = event_emitter
        self.workspace = workspace
        self._agents: dict[str, LiveAgent] = {}  # agent_id → LiveAgent
        self._thread_agents: dict[str, str] = {}  # thread_id → agent_id
        self._lock = asyncio.Lock()

    async def spawn(
        self,
        agent_type: str,
        task: str,
        *,
        parent_agent_id: str | None = None,
        label: str | None = None,
        fork_history: bool = False,
        model_override: str | None = None,
    ) -> LiveAgent:
        """Spawn a new agent to handle a task.

        Args:
            agent_type: Name of the agent type (e.g. "code-agent")
            task: The task description
            parent_agent_id: ID of the spawning agent (None for root)
            label: Human-readable task label
            fork_history: Whether to copy parent's conversation history
            model_override: Override the default model for this agent

        Returns:
            LiveAgent handle for the spawned agent
        """
        metadata = self.registry.resolve(agent_type)
        agent_id = str(uuid.uuid4())[:12]
        thread_id = f"{self.session_id}:{agent_id}"

        agent = LiveAgent(
            agent_id=agent_id,
            thread_id=thread_id,
            metadata=metadata,
            state=AgentStateMachine(),
            parent_agent_id=parent_agent_id,
        )
        # AgentStateMachine starts at IDLE — no transition needed

        async with self._lock:
            self._agents[agent_id] = agent
            self._thread_agents[thread_id] = agent_id

        await self._events.emit(SubAgentSpawnedEvent(
            parent_turn_id=parent_agent_id or self.session_id,
            sub_agent_id=agent_id,
            sub_thread_id=thread_id,
            agent_type=agent_type,
            task_label=label or task[:40],
        ))

        logger.info(
            "Spawned agent {} of type {} for thread {}",
            agent_id, agent_type, thread_id,
        )

        return agent

    async def fork(
        self,
        source_thread_id: str,
        agent_type: str | None = None,
        last_n_turns: int | None = None,
    ) -> LiveAgent:
        """Fork an existing thread into a new agent.

        Args:
            source_thread_id: The thread to fork from
            agent_type: Agent type for the fork (defaults to source agent type)
            last_n_turns: Copy only the last N turns of history

        Returns:
            LiveAgent handle for the forked agent
        """
        source_agent_id = self._thread_agents.get(source_thread_id)
        if source_agent_id is None:
            raise ValueError(f"Unknown thread: {source_thread_id}")

        source = self._agents[source_agent_id]
        fork_type = agent_type or source.metadata.name

        metadata = self.registry.resolve(fork_type)
        agent_id = str(uuid.uuid4())[:12]
        fork_thread_id = f"{self.session_id}:{agent_id}"

        agent = LiveAgent(
            agent_id=agent_id,
            thread_id=fork_thread_id,
            metadata=metadata,
            state=AgentStateMachine(),
            parent_agent_id=source.parent_agent_id,
        )

        async with self._lock:
            self._agents[agent_id] = agent
            self._thread_agents[fork_thread_id] = agent_id

        logger.info(
            "Forked thread {} → {} (type: {})",
            source_thread_id, fork_thread_id, fork_type,
        )

        return agent

    async def kill(self, agent_id: str) -> None:
        """Kill a running agent."""
        async with self._lock:
            agent = self._agents.pop(agent_id, None)
            if agent is None:
                return
            self._thread_agents.pop(agent.thread_id, None)
            agent.state.transition(AgentStatus.ABORTED)

        logger.info("Killed agent {}", agent_id)

    async def get_status(self, agent_id: str) -> AgentStatus:
        """Get the current status of an agent."""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent: {agent_id}")
        return agent.state.current

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents with their status."""
        return [
            {
                "agent_id": a.agent_id,
                "thread_id": a.thread_id,
                "type": a.metadata.display_name,
                "status": a.state.current.value,
                "parent": a.parent_agent_id,
                "label": a.metadata.description,
            }
            for a in self._agents.values()
        ]
