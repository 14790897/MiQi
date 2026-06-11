"""Tests verifying all tool calls go through ToolOrchestrator (Phase 10).

These tests would FAIL before Phase 10 fixes:
- Parallel branch called execute_concurrent() directly
- Missing orchestrator silently produced empty results
- No TurnContext was created for main agent
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


def _make_temp_dir():
    """TemporaryDirectory with cleanup error tolerance (for Windows sqlite locks)."""
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def _make_fake_response(*, content="", tool_calls=None, has_tool_calls=None):
    """Build a minimal fake provider response."""
    class FakeResponse:
        def __init__(self):
            self.content = content
            self.tool_calls = tool_calls or []
            self._has_tool_calls = (
                has_tool_calls if has_tool_calls is not None
                else bool(tool_calls)
            )
            self.reasoning_content = None  # Required by AgentLoop
            self.usage: dict[str, int] = {}  # Required by AgentLoop
        @property
        def has_tool_calls(self):
            return self._has_tool_calls
        @property
        def finish_reason(self):
            return "stop"
    return FakeResponse()


def _make_fake_tool_call(name, args, tc_id="tc-1"):
    """Build a minimal fake tool call."""
    class FakeToolCall:
        def __init__(self):
            self.name = name
            self.arguments = args
            self.id = tc_id
    return FakeToolCall()


def _make_minimal_orchestrator():
    """Create a minimal ToolOrchestrator for testing."""
    from miqi.execution.orchestrator import ToolOrchestrator
    from miqi.execution.permission_engine import PermissionEngine
    from miqi.execution.sandbox_policy import SandboxPolicyEngine
    from miqi.execution.hook_runtime import HookRuntime

    emitter = MagicMock()
    emitter.emit = AsyncMock()
    return ToolOrchestrator(
        permission_engine=PermissionEngine(),
        sandbox_engine=SandboxPolicyEngine(),
        hook_runtime=HookRuntime(),
        tool_registry=None,
        event_emitter=emitter,
    )


# ---------------------------------------------------------------------------
# Task 10.1: Parallel tool calls must go through orchestrator, not execute_concurrent
# ---------------------------------------------------------------------------

def test_parallel_tool_calls_use_orchestrator_not_execute_concurrent():
    """Parallel tool batch must route through orchestrator, not registry."""
    from miqi.agent.loop import AgentLoop
    from miqi.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock()

    with _make_temp_dir() as tmp:
        workspace = Path(tmp)
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace, model="test-model")

        # Set up orchestrator
        orchestrator = _make_minimal_orchestrator()
        orchestrator.tools = loop.tools
        loop.set_orchestrator(orchestrator)

        # Set up fake execute_concurrent that should NOT be called
        original_execute_concurrent = AsyncMock(return_value=[])
        loop.tools.execute_concurrent = original_execute_concurrent

        # Set up fake execute
        execute_mock = AsyncMock()

        async def _fake_execute(ctx):
            ctx.result = f"result-for-{ctx.tool_name}"
            ctx.duration_ms = 10
            return ctx
        execute_mock.side_effect = _fake_execute

        orchestrator.execute = execute_mock

        # Force parallelization
        original_should_parallelize = loop.tools.should_parallelize
        loop.tools.should_parallelize = lambda _tc: True

        try:
            tc1 = _make_fake_tool_call("read_file", {"path": "/tmp/a.txt"}, "tcid-1")
            tc2 = _make_fake_tool_call("read_file", {"path": "/tmp/b.txt"}, "tcid-2")
            response1 = _make_fake_response(tool_calls=[tc1, tc2], has_tool_calls=True)
            response2 = _make_fake_response(content="All done.", has_tool_calls=False)
            provider.chat.side_effect = [response1, response2]

            result = asyncio.run(loop._run_agent_loop(
                [{"role": "user", "content": "test"}],
                session_key="test:parallel",
            ))
        finally:
            loop.tools.should_parallelize = original_should_parallelize

        # execute_concurrent was NOT called
        original_execute_concurrent.assert_not_called()

        # orchestrator.execute was called for each tool
        assert execute_mock.call_count >= 2

        # final content was reached
        assert result[0] is not None


# ---------------------------------------------------------------------------
# Task 10.2: Fail fast when orchestrator is missing
# ---------------------------------------------------------------------------

def test_agent_loop_raises_when_no_orchestrator():
    """AgentLoop._run_agent_loop must raise RuntimeError if _orchestrator is None."""
    from miqi.agent.loop import AgentLoop
    from miqi.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock()

    with _make_temp_dir() as tmp:
        workspace = Path(tmp)
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace, model="test-model")
        # Do NOT set orchestrator
        loop._orchestrator = None

        with __import__("pytest").raises(RuntimeError, match="ToolOrchestrator must be configured"):
            asyncio.run(loop._run_agent_loop(
                [{"role": "user", "content": "test"}],
                session_key="test:no-orch",
            ))


def test_set_orchestrator_method():
    """AgentLoop.set_orchestrator() sets _orchestrator and wires tools."""
    from miqi.agent.loop import AgentLoop
    from miqi.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock()

    with _make_temp_dir() as tmp:
        workspace = Path(tmp)
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace, model="test-model")

        orchestrator = _make_minimal_orchestrator()
        loop.set_orchestrator(orchestrator)

        assert loop._orchestrator is orchestrator
        assert orchestrator.tools is loop.tools


# ---------------------------------------------------------------------------
# Task 10.6: TurnContext is created and exposed during processing
# ---------------------------------------------------------------------------

def test_turn_context_created_and_cleared():
    """Main AgentLoop must expose current_turn during processing, clear after."""
    from miqi.agent.loop import AgentLoop
    from miqi.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    response = _make_fake_response(content="Hello!", has_tool_calls=False)
    provider.chat = AsyncMock(return_value=response)

    with _make_temp_dir() as tmp:
        workspace = Path(tmp)
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace, model="test-model")

        orchestrator = _make_minimal_orchestrator()
        orchestrator.tools = loop.tools
        loop.set_orchestrator(orchestrator)

        captured_turns = []

        async def _capturing_chat(**kwargs):
            captured_turns.append(loop.current_turn)
            return response

        provider.chat = _capturing_chat

        # Use process_direct to go through TurnContext creation
        result = asyncio.run(loop.process_direct(
            content="Hello",
            session_key="test:turnctx",
        ))

        assert "Hello" in result, f"Unexpected result: {result}"
        # current_turn cleared by finally block
        assert loop.current_turn is None, "current_turn must be cleared after processing"
        assert len(captured_turns) >= 1
        assert captured_turns[0] is not None
        assert captured_turns[0].thread_id == "test:turnctx"
