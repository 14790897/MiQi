"""Tests for miqi.runtime.agent_control."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from miqi.runtime.agent_registry import AgentRegistry
from miqi.runtime.agent_control import AgentControl, LiveAgent
from miqi.protocol.events import AgentStatus


@pytest.fixture
def event_emitter():
    emitter = AsyncMock()
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def agent_control(tmp_path, event_emitter):
    registry = AgentRegistry()
    return AgentControl(
        session_id="test-session",
        registry=registry,
        event_emitter=event_emitter,
        workspace=tmp_path,
    )


@pytest.mark.asyncio
async def test_spawn_agent(agent_control, event_emitter):
    agent = await agent_control.spawn(
        agent_type="code-agent",
        task="Fix the lint errors",
        label="lint-fix",
    )
    assert agent.agent_id
    assert agent.metadata.name == "code-agent"
    assert agent.state.current == AgentStatus.IDLE
    event_emitter.emit.assert_called()


@pytest.mark.asyncio
async def test_list_agents(agent_control):
    await agent_control.spawn("code-agent", "task 1", label="a")
    await agent_control.spawn("doc-agent", "task 2", label="b")
    agents = agent_control.list_agents()
    assert len(agents) == 2
    types = {a["type"] for a in agents}
    assert types == {"Code Agent", "Document Agent"}


@pytest.mark.asyncio
async def test_kill_agent(agent_control):
    agent = await agent_control.spawn("code-agent", "task", label="test")
    agent_id = agent.agent_id
    await agent_control.kill(agent_id)
    with pytest.raises(KeyError):
        await agent_control.get_status(agent_id)


@pytest.mark.asyncio
async def test_get_status(agent_control):
    agent = await agent_control.spawn("code-agent", "task", label="test")
    status = await agent_control.get_status(agent.agent_id)
    assert status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_spawn_unknown_type_raises(agent_control):
    with pytest.raises(KeyError, match="Unknown agent type"):
        await agent_control.spawn("nonexistent", "task")


@pytest.mark.asyncio
async def test_spawn_emits_event(agent_control, event_emitter):
    await agent_control.spawn("research-agent", "Research X", label="research-x")
    # Should emit SubAgentSpawnedEvent
    call_args = event_emitter.emit.call_args
    assert call_args is not None


@pytest.mark.asyncio
async def test_kill_updates_status(agent_control):
    agent = await agent_control.spawn("code-agent", "task", label="test")
    await agent_control.kill(agent.agent_id)
    # agent should be removed and status unavailable
    with pytest.raises(KeyError):
        await agent_control.get_status(agent.agent_id)


@pytest.mark.asyncio
async def test_spawn_main_agent(agent_control, event_emitter):
    agent = await agent_control.spawn("main", "General task", label="main-task")
    assert agent.metadata.name == "main"
    assert agent.metadata.max_iterations == 40


@pytest.mark.asyncio
async def test_fork_creates_new_agent(agent_control, event_emitter):
    parent = await agent_control.spawn("code-agent", "test task", label="parent")
    child = await agent_control.fork(parent.thread_id)
    assert child.agent_id != parent.agent_id
    assert child.thread_id != parent.thread_id


@pytest.mark.asyncio
async def test_fork_unknown_thread_raises(agent_control):
    with pytest.raises(ValueError, match="Unknown thread"):
        await agent_control.fork("nonexistent-thread")
