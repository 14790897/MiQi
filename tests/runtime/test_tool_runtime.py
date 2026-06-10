"""Tests for ToolRuntime (Phase 12.1)."""

from unittest.mock import AsyncMock

import pytest

from miqi.runtime.tool_runtime import ToolRuntime


class _FakeTurnContext:
    turn_id = "turn-1"
    thread_id = "thread-1"

    class _Meta:
        name = "code-agent"
    agent_metadata = _Meta()


class _FakeToolCall:
    def __init__(self, name="read_file", args=None, tc_id="tc-1"):
        self.name = name
        self.arguments = args or {"path": "/tmp/x"}
        self.id = tc_id


@pytest.fixture
def fake_orchestrator():
    orchestrator = AsyncMock()
    async def _execute(ctx):
        ctx.result = "ok"
        ctx.duration_ms = 5
        return ctx
    orchestrator.execute.side_effect = _execute
    return orchestrator


@pytest.fixture
def fake_turn_context():
    return _FakeTurnContext()


@pytest.fixture
def fake_tool_call():
    return _FakeToolCall()


# ── Single execution ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_runtime_executes_single_call_through_orchestrator(
    fake_turn_context, fake_orchestrator, fake_tool_call,
):
    runtime = ToolRuntime(orchestrator=fake_orchestrator)

    result = await runtime.execute_one(fake_turn_context, fake_tool_call)

    assert result.tool_call_id == fake_tool_call.id
    fake_orchestrator.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_runtime_executes_parallel_calls_through_orchestrator(
    fake_turn_context, fake_orchestrator, fake_tool_call,
):
    runtime = ToolRuntime(orchestrator=fake_orchestrator)

    results = await runtime.execute_many(
        fake_turn_context, [fake_tool_call, fake_tool_call],
    )

    assert len(results) == 2
    assert fake_orchestrator.execute.await_count == 2


def test_tool_runtime_requires_orchestrator():
    """ToolRuntime raises RuntimeError when orchestrator is None."""
    with pytest.raises(RuntimeError, match="ToolRuntime requires a ToolOrchestrator"):
        ToolRuntime(orchestrator=None)
