"""Tests for miqi.agent.tools.spawn — Phase 13 updated.

Verifies that SpawnTool requires AgentControl (no legacy fallback):
- When AgentControl is wired, only AgentControl.spawn() is used.
- When AgentControl is None, RuntimeError is raised.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_subagent_manager():
    """Create a mock SubagentManager (kept for dead code compatibility)."""
    mgr = MagicMock()
    mgr.spawn = AsyncMock(return_value="legacy-result")
    return mgr


@pytest.fixture
def mock_agent_control():
    """Create a mock AgentControl."""
    class _FakeAgent:
        agent_id = "agent-abc123"
        thread_id = "thread-xyz789"

    ac = MagicMock()
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


def test_spawn_tool_requires_agent_control(mock_subagent_manager):
    """When _agent_control is None, SpawnTool raises RuntimeError (Phase 13).

    The legacy SubagentManager fallback has been removed.
    """
    from miqi.agent.tools.spawn import SpawnTool

    tool = SpawnTool(
        manager=mock_subagent_manager,
        agent_control=None,
    )

    with pytest.raises(RuntimeError, match="AgentControl"):
        asyncio.run(tool.execute(task="test task", label="test-label"))

    # Legacy manager was NOT called
    mock_subagent_manager.spawn.assert_not_called()


def test_spawn_tool_no_longer_falls_back_on_agent_control_failure(
    mock_subagent_manager, mock_agent_control,
):
    """When AgentControl.spawn() raises, exception propagates (no fallback)."""
    from miqi.agent.tools.spawn import SpawnTool

    mock_agent_control.spawn.side_effect = RuntimeError("AgentControl unavailable")

    tool = SpawnTool(
        manager=mock_subagent_manager,
        agent_control=mock_agent_control,
    )

    with pytest.raises(RuntimeError, match="AgentControl unavailable"):
        asyncio.run(tool.execute(task="test task", label="test-label"))

    # AgentControl was tried
    mock_agent_control.spawn.assert_called_once()
    # Legacy manager was NOT called (no fallback)
    mock_subagent_manager.spawn.assert_not_called()
