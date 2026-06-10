"""Spawn tool for creating background subagents."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from loguru import logger

from miqi.agent.tools.base import Tool

if TYPE_CHECKING:
    from miqi.agent.subagent import SubagentManager


class SpawnTool(Tool):
    """
    Tool to spawn a subagent for background task execution.

    The subagent runs asynchronously and announces its result back
    to the main agent when complete.
    """

    def __init__(
        self,
        manager: "SubagentManager",
        agent_control: Any = None,
        event_emitter: Any = None,
    ):
        self._manager = manager
        self._agent_control = agent_control
        self._event_emitter = event_emitter
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the origin context for subagent announcements."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "Spawn a subagent to handle a task in the background. "
            "Use this for complex or time-consuming tasks that can run independently. "
            "The subagent will complete the task and report back when done."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                },
            },
            "required": ["task"],
        }

    async def execute(self, task: str, label: str | None = None, **kwargs: Any) -> str:
        """Spawn a subagent to execute the given task."""
        # Phase 2: register with AgentControl before spawning via SubagentManager
        display_label = label or (task[:30] + "..." if len(task) > 30 else task)
        agent_id = str(uuid.uuid4())[:12]

        if self._agent_control is not None:
            try:
                agent = await self._agent_control.spawn(
                    agent_type="code-agent",
                    task=task,
                    label=display_label,
                )
                agent_id = agent.agent_id
                logger.info(
                    "Subagent registered with AgentControl: {} ({})",
                    agent_id, display_label,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to register subagent with AgentControl: {}", exc
                )

        result = await self._manager.spawn(
            task=task,
            label=label,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
        )

        return result
