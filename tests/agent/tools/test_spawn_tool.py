"""Tests for miqi.agent.tools.spawn — Phase 10 post-audit.

Verifies that SpawnTool does not double-launch:
- When AgentControl is wired, only AgentControl.spawn() is used.
- When AgentControl is None, legacy SubagentManager.spawn() fallback works.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_subagent_manager():
    """Create a mock SubagentManager."""
    mgr = AsyncMock()
    mgr.spawn = AsyncMock(return_value="legacy-result")
    return mgr


@pytest.fixture
def mock_agent_control():
    """Create a mock AgentControl."""
    from unittest.mock import AsyncMock

    class _FakeAgent:
        agent_id = "agent-abc123"
        thread_id = "thread-xyz789"

    ac = AsyncMock()
    ac.spawn = AsyncMock(return_value=_FakeAgent())
    return ac


def test_spawn_tool_uses_agent_control_when_available(mock_subagent_manager, mock_agent_control):
    """When _agent_control is set, SpawnTool uses it and NOT legacy manager."""
    from miqi.agent.tools.spawn import SpawnTool

    tool = SpawnTool(
        manager=mock_subagent_manager,
        agent_control=mock_agent_control,
    )

    result = asyncio.run(tool.execute(task="test task", label="test-label"))

    # AgentControl.spawn() was called
    mock_agent_control.spawn.assert_called_once()
    # Legacy SubagentManager.spawn() was NOT called
    mock_subagent_manager.spawn.assert_not_called()
    # Result includes agent_id and thread_id
    assert "agent-abc123" in result
    assert "thread-xyz789" in result


def test_spawn_tool_falls_back_when_agent_control_is_none(mock_subagent_manager):
    """When _agent_control is None, SpawnTool falls back to legacy manager."""
    from miqi.agent.tools.spawn import SpawnTool

    tool = SpawnTool(
        manager=mock_subagent_manager,
        agent_control=None,
    )

    result = asyncio.run(tool.execute(task="test task", label="test-label"))

    # Legacy manager was called
    mock_subagent_manager.spawn.assert_called_once()
    assert result == "legacy-result"


def test_spawn_tool_falls_back_when_agent_control_spawn_fails(
    mock_subagent_manager, mock_agent_control,
):
    """When AgentControl.spawn() raises, fall back to legacy manager."""
    from miqi.agent.tools.spawn import SpawnTool

    mock_agent_control.spawn.side_effect = RuntimeError("AgentControl unavailable")

    tool = SpawnTool(
        manager=mock_subagent_manager,
        agent_control=mock_agent_control,
    )

    result = asyncio.run(tool.execute(task="test task", label="test-label"))

    # AgentControl was tried
    mock_agent_control.spawn.assert_called_once()
    # Legacy manager was called as fallback
    mock_subagent_manager.spawn.assert_called_once()
    assert result == "legacy-result"
