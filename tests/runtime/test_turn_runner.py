"""Tests for TurnRunner (Phase 12.3)."""

from unittest.mock import AsyncMock

import pytest

from miqi.runtime.turn_runner import TurnRunner


class _FakeTurnContext:
    turn_id = "turn-1"
    thread_id = "thread-1"
    model = "test-model"
    temperature = 0.0
    max_tokens = 100

    class _Meta:
        name = "code-agent"
    agent_metadata = _Meta()


class _FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self._has_tool_calls = bool(tool_calls)

    @property
    def has_tool_calls(self):
        return self._has_tool_calls


class _FakeToolCall:
    def __init__(self, name="read_file", args=None, tc_id="tc-1"):
        self.name = name
        self.arguments = args or {"path": "/tmp/x"}
        self.id = tc_id
        self.arguments_json = '{"path": "/tmp/x"}'


@pytest.fixture
def fake_turn_context():
    return _FakeTurnContext()


@pytest.fixture
def fake_tool_runtime():
    runtime = AsyncMock()

    class _Ctx:
        def __init__(self, tc):
            self.tool_call_id = tc.id
            self.result = f"result-for-{tc.name}"

    async def _fake_execute_many(turn, calls):
        return [_Ctx(c) for c in calls]

    runtime.execute_many.side_effect = _fake_execute_many
    return runtime


@pytest.fixture
def fake_context_runtime():
    from miqi.runtime.context_runtime import ContextRuntime
    return ContextRuntime()


@pytest.fixture
def turn_runner(fake_tool_runtime, fake_context_runtime):
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_FakeResponse(content="final answer"))
    return TurnRunner(
        provider=provider,
        tool_runtime=fake_tool_runtime,
        context_runtime=fake_context_runtime,
        event_emitter=AsyncMock(),
        max_iterations=3,
    ), provider


# ── Tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_turn_runner_returns_final_response(turn_runner, fake_turn_context):
    runner, provider = turn_runner

    result = await runner.run(
        turn=fake_turn_context,
        user_content="hello",
        system_prompt="system",
        tools=[],
    )

    assert result.final_content == "final answer"
    assert result.messages[-1]["role"] == "assistant"
    provider.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_runner_handles_tool_calls(turn_runner, fake_turn_context, fake_tool_runtime):
    runner, provider = turn_runner

    # First response: tool calls
    tc = _FakeToolCall("read_file")
    provider.chat.side_effect = [
        _FakeResponse(tool_calls=[tc]),
        _FakeResponse(content="done after tools"),
    ]

    result = await runner.run(
        turn=fake_turn_context,
        user_content="task",
        system_prompt="sys",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )

    assert result.final_content == "done after tools"
    assert "read_file" in result.tools_used
    assert provider.chat.await_count == 2
    fake_tool_runtime.execute_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_runner_exhausts_iterations(turn_runner, fake_turn_context):
    runner, provider = turn_runner

    # Always return tool calls — forces exhaustion
    provider.chat.return_value = _FakeResponse(tool_calls=[_FakeToolCall()])
    runner._max_iterations = 2  # Small cap for fast test

    result = await runner.run(
        turn=fake_turn_context,
        user_content="endless task",
        system_prompt="sys",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )

    assert "Reached maximum iterations" in result.final_content
