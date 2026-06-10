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


# ---------------------------------------------------------------------------
# Phase 10: Tool definitions, orchestrator enforcement, result persistence
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_tool_registry():
    """Create a minimal ToolRegistry mock with get_definitions for testing."""
    from unittest.mock import MagicMock

    registry = MagicMock()
    registry.get_definitions.return_value = [
        {
            "type": "function",
            "function": {"name": "read_file", "description": "Read a file", "parameters": {}},
        },
        {
            "type": "function",
            "function": {"name": "exec", "description": "Execute command", "parameters": {}},
        },
        {
            "type": "function",
            "function": {"name": "docx_read", "description": "Read docx", "parameters": {}},
        },
    ]
    return registry


@pytest.fixture
def fake_provider():
    """Create a provider that records its calls and returns responses."""
    from unittest.mock import MagicMock

    class FakeProvider:
        def __init__(self):
            self.chat_calls: list[dict] = []
            self.response_sequence: list = []

        async def chat(self, **kwargs):
            self.chat_calls.append(kwargs)
            if self.response_sequence:
                return self.response_sequence.pop(0)
            # Default: final answer
            return _FakeResponse(content="Done.", tool_calls=[])

    return FakeProvider()


class _FakeToolCall:
    """Minimal fake for response.tool_calls entries."""
    def __init__(self, name, args, tc_id="tcid"):
        self.name = name
        self.arguments = args
        self.id = tc_id


class _FakeResponse:
    """Minimal fake response object."""
    def __init__(self, content="", tool_calls=None, finish_reason="stop"):
        self.content = content
        self.tool_calls = tool_calls or []
        self._has_tool_calls = bool(tool_calls)
        self.finish_reason = finish_reason

    @property
    def has_tool_calls(self):
        return self._has_tool_calls


# Task 10.3: Sub-agents receive role-filtered tool definitions
@pytest.mark.asyncio
async def test_sub_agent_receives_role_filtered_tools(
    tmp_path, event_emitter, fake_provider, fake_tool_registry,
):
    """code-agent should only see code tools, not doc tools."""
    from miqi.runtime.agent_registry import AgentRegistry
    from miqi.runtime.agent_control import AgentControl

    control = AgentControl(
        session_id="test-session",
        registry=AgentRegistry(),
        event_emitter=event_emitter,
        workspace=tmp_path,
        provider=None,  # Don't auto-start background task
        tool_registry=fake_tool_registry,
        orchestrator="placeholder",  # Won't be used if agent has no tool calls
    )

    # Spawn agent (no auto-start since provider is None)
    agent = await control.spawn("code-agent", "test", label="test-role-tools")

    # Set provider after spawn, then call _run_agent directly
    control._provider = fake_provider
    fake_provider.response_sequence = [
        _FakeResponse(content="Done.", tool_calls=[]),
    ]

    await control._run_agent(agent, "test task")

    # Provider should have been called with role-filtered tools
    assert len(fake_provider.chat_calls) >= 1
    tools_arg = fake_provider.chat_calls[0].get("tools")
    assert tools_arg is not None, "Sub-agent must receive tool definitions (was None)"

    tool_names = {t["function"]["name"] for t in tools_arg}
    # code-agent should have read_file and exec (code tools)
    assert "read_file" in tool_names
    assert "exec" in tool_names
    # code-agent should NOT have doc tools
    assert "docx_read" not in tool_names


# Task 10.4: Orchestrator required before sub-agent tool execution
@pytest.mark.asyncio
async def test_sub_agent_raises_when_no_orchestrator_for_tools(
    tmp_path, event_emitter, fake_provider, fake_tool_registry,
):
    """Sub-agent must raise RuntimeError when tools are called but no orchestrator."""
    from miqi.runtime.agent_registry import AgentRegistry
    from miqi.runtime.agent_control import AgentControl

    control = AgentControl(
        session_id="test-session",
        registry=AgentRegistry(),
        event_emitter=event_emitter,
        workspace=tmp_path,
        provider=None,  # Don't auto-start
        tool_registry=fake_tool_registry,
        orchestrator=None,  # No orchestrator!
    )

    agent = await control.spawn("code-agent", "test", label="test-no-orch")

    # Set provider after spawn to avoid auto-start
    control._provider = fake_provider
    fake_provider.response_sequence = [
        _FakeResponse(
            tool_calls=[_FakeToolCall("read_file", {"path": "/tmp/x"}, "tc-1")],
        ),
    ]

    # _run_agent should set error state
    await control._run_agent(agent, "test task")

    # Agent should have transitioned to ERROR with a clear error
    assert agent.error is not None, "Agent should have recorded an error"
    assert "ToolOrchestrator must be configured" in agent.error
    assert agent.state.current.value in ("error", "aborted")


# Task 10.5: Sub-agent results are persisted and exposed via list/detail
@pytest.mark.asyncio
async def test_sub_agent_result_persisted(
    tmp_path, event_emitter, fake_provider, fake_tool_registry,
):
    """After completion, sub-agent result/error/messages are stored on LiveAgent."""
    from miqi.runtime.agent_registry import AgentRegistry
    from miqi.runtime.agent_control import AgentControl

    control = AgentControl(
        session_id="test-session",
        registry=AgentRegistry(),
        event_emitter=event_emitter,
        workspace=tmp_path,
        provider=None,  # Don't auto-start
        tool_registry=fake_tool_registry,
        orchestrator="placeholder",
    )

    agent = await control.spawn("code-agent", "Write a test", label="test-persist")

    # Set provider after spawn
    control._provider = fake_provider
    fake_provider.response_sequence = [
        _FakeResponse(content="Task complete. Here is the code.", tool_calls=[]),
    ]

    await control._run_agent(agent, "Write a test")

    # Result persisted
    assert agent.result is not None
    assert "Task complete" in agent.result
    assert agent.completed_at is not None
    # Messages recorded
    assert len(agent.messages) >= 2  # system + user + assistant
    roles = {m["role"] for m in agent.messages}
    assert "assistant" in roles

    # list_agents includes result_preview
    agents_list = control.list_agents()
    assert len(agents_list) == 1
    assert "result_preview" in agents_list[0]
    assert len(agents_list[0]["result_preview"]) <= 200
    assert "Task complete" in agents_list[0]["result_preview"]

    # get_agent_detail returns full info
    detail = control.get_agent_detail(agent.agent_id)
    assert detail["result"] == agent.result
    assert detail["messages"] is agent.messages
    assert detail["completed_at"] == agent.completed_at


@pytest.mark.asyncio
async def test_get_agent_detail_unknown_raises(tmp_path, event_emitter):
    """get_agent_detail should raise KeyError for unknown agent IDs."""
    from miqi.runtime.agent_registry import AgentRegistry
    from miqi.runtime.agent_control import AgentControl

    control = AgentControl(
        session_id="test-session",
        registry=AgentRegistry(),
        event_emitter=event_emitter,
        workspace=tmp_path,
    )

    with pytest.raises(KeyError, match="Unknown agent"):
        control.get_agent_detail("nonexistent")
