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
    TurnStartedEvent,
    TurnCompleteEvent,
    ToolCallBeginEvent,
    ToolCallEndEvent,
    AgentMessageEvent,
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

    async def _run_agent(self, agent: LiveAgent, task: str) -> None:
        """Execute the agent's task loop.

        This is the core integration point between:
        - AgentControl (multi-agent lifecycle)
        - TurnContext (per-turn configuration)
        - ToolOrchestrator (unified tool execution)
        - EventEmitter (typed event output)

        For the main agent, this is called from the existing AgentLoop
        after migration. For sub-agents, this is called from spawn().
        """
        import uuid as _uuid
        import time as _time
        import json
        import re as _re

        turn_id = str(_uuid.uuid4())[:12]
        tools_used: list[str] = []

        try:
            agent.state.transition(AgentStatus.THINKING)

            # Emit turn started
            await self._events.emit(TurnStartedEvent(
                turn_id=turn_id,
                agent_name=agent.metadata.display_name,
                thread_id=agent.thread_id,
            ))

            # Build TurnContext
            from miqi.runtime.turn_context import TurnContext
            turn_ctx = TurnContext(
                turn_id=turn_id,
                agent_metadata=agent.metadata,
                thread_id=agent.thread_id,
                workspace=self.workspace,
                model="default",
                provider=None,  # Set by caller after spawn
                temperature=0.1,
                max_tokens=8192,
            )

            # Build initial messages
            messages: list[dict] = [
                {"role": "system", "content": agent.metadata.system_prompt},
                {"role": "user", "content": task},
            ]

            # ── Main turn loop ──────────────────────────────────
            final_content: str | None = None
            max_iterations = agent.metadata.max_iterations

            for iteration in range(1, max_iterations + 1):
                # 1. Call LLM (requires provider to be wired)
                if turn_ctx.provider is None:
                    final_content = (
                        "Agent provider not wired. "
                        "AgentControl._run_agent() requires a provider "
                        "to be set on TurnContext.provider before execution. "
                        "In production, this is done by AgentLoop via BridgeServer."
                    )
                    break

                response = await turn_ctx.provider.chat(
                    messages=messages,
                    tools=None,
                    model=turn_ctx.model,
                    temperature=turn_ctx.temperature,
                    max_tokens=turn_ctx.max_tokens,
                )

                # 2. Handle tool calls
                if response.has_tool_calls:
                    agent.state.transition(AgentStatus.EXECUTING)

                    tool_call_dicts = []
                    for tc in response.tool_calls:
                        tools_used.append(tc.name)

                        # Emit tool begin event
                        hint = self._format_tool_hint(tc.name, tc.arguments)
                        await self._events.emit(ToolCallBeginEvent(
                            turn_id=turn_id,
                            tool_call_id=tc.id,
                            tool_name=tc.name,
                            tool_display=hint,
                            arguments=tc.arguments,
                        ))

                        # Route through orchestrator if available
                        orchestrator = getattr(self, '_orchestrator', None)
                        if orchestrator is not None:
                            from miqi.execution.orchestrator import ToolExecutionContext
                            ctx = ToolExecutionContext(
                                tool_name=tc.name,
                                tool_call_id=tc.id,
                                arguments=tc.arguments,
                                turn_id=turn_id,
                                thread_id=agent.thread_id,
                                agent_type=agent.metadata.name,
                            )
                            ctx = await orchestrator.execute(ctx)
                            result = ctx.result or ""
                            success = not (
                                isinstance(result, str)
                                and result.startswith("Error")
                            )
                            duration = ctx.duration_ms
                        else:
                            result = f"Error: no orchestrator available for {tc.name}"
                            success = False
                            duration = 0

                        # Emit tool end event
                        preview = (result or "")[:200]
                        await self._events.emit(ToolCallEndEvent(
                            turn_id=turn_id,
                            tool_call_id=tc.id,
                            tool_name=tc.name,
                            success=success,
                            output_preview=preview,
                            output_size=len(result or ""),
                            duration_ms=duration,
                        ))

                        # Build tool call dict for message history
                        tool_call_dicts.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(
                                    tc.arguments, ensure_ascii=False
                                ),
                            },
                        })

                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "content": result or "",
                        })

                    # Add assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": tool_call_dicts,
                    })

                    # Reflect prompt for next iteration
                    messages.append({
                        "role": "system",
                        "content": (
                            "Check if the task is complete. "
                            "If more tools are needed, call them now. "
                            "If the task is done, provide a clear final answer."
                        ),
                    })

                    agent.state.transition(AgentStatus.THINKING)

                else:
                    # No tool calls — final response
                    final_content = self._strip_think(response.content)
                    if final_content:
                        await self._events.emit(AgentMessageEvent(
                            turn_id=turn_id,
                            content=final_content,
                            finish_reason=(
                                response.finish_reason or "stop"
                            ),
                        ))
                    break

            # Handle iteration exhaustion
            if final_content is None:
                summary = (
                    ", ".join(dict.fromkeys(tools_used))
                    if tools_used else "none"
                )
                final_content = (
                    f"Reached maximum iterations ({max_iterations}). "
                    f"Tools used: {summary}. "
                    f"Try breaking your task into smaller steps."
                )

            # Turn complete
            agent.state.transition(AgentStatus.COMPLETED)
            await self._events.emit(TurnCompleteEvent(
                turn_id=turn_id,
                thread_id=agent.thread_id,
                outcome="success",
                tools_used=list(dict.fromkeys(tools_used)),
            ))
            await self._events.emit(SubAgentCompletedEvent(
                sub_agent_id=agent.agent_id,
                sub_thread_id=agent.thread_id,
                outcome="success",
                summary=(final_content or "")[:100],
            ))

        except asyncio.CancelledError:
            agent.state.transition(AgentStatus.ABORTED)
        except Exception as e:
            agent.state.transition(AgentStatus.ERROR)
            logger.error(
                "Agent {} turn error: {}", agent.agent_id, e
            )
            await self._events.emit(ErrorEvent(
                turn_id=turn_id,
                severity=EventSeverity.ERROR,
                message=str(e),
                recoverable=False,
            ))

    @staticmethod
    def _format_tool_hint(name: str, args: dict) -> str:
        """Format a tool call as a concise display hint."""
        val = next(iter(args.values()), "") if args else ""
        if not isinstance(val, str):
            return name
        if len(val) > 50:
            return f'{name}("{val[:50]}…")'
        return f'{name}("{val}")'

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks from model output."""
        if not text:
            return None
        import re
        result = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        return result or None
