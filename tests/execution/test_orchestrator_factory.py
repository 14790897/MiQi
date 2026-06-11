"""Tests for miqi.execution.factory — shared orchestrator factory (Phase 10 post-audit)."""

from unittest.mock import AsyncMock


def test_create_default_orchestrator_noop_emitter_when_none():
    """When event_emitter is None, a NoopEmitter is used instead of crashing."""
    from miqi.execution.factory import create_default_orchestrator

    orchestrator = create_default_orchestrator(
        tool_registry=None,
        event_emitter=None,
    )

    assert orchestrator is not None
    assert orchestrator.events is not None
    # NoopEmitter should not raise on emit
    import asyncio
    asyncio.run(orchestrator.events.emit({"type": "test"}))


def test_create_default_orchestrator_with_event_emitter():
    """When event_emitter is provided, it is used directly."""
    from miqi.execution.factory import create_default_orchestrator

    emitter = AsyncMock()
    orchestrator = create_default_orchestrator(
        tool_registry=None,
        event_emitter=emitter,
    )

    assert orchestrator.events is emitter


def test_create_default_orchestrator_permanent_allowlist():
    """Permanent allowlist is passed through to PermissionEngine."""
    from miqi.execution.factory import create_default_orchestrator

    orchestrator = create_default_orchestrator(
        tool_registry=None,
        permanent_allowlist={"echo hello"},
    )

    assert "echo hello" in orchestrator.permissions.permanent_allowlist


def test_configure_agent_orchestrator_wires_tools():
    """configure_agent_orchestrator ensures orchestrator.tools == agent.tools."""
    from miqi.execution.factory import configure_agent_orchestrator
    from miqi.agent.loop import AgentLoop
    from miqi.bus.queue import MessageBus
    from pathlib import Path
    import tempfile

    bus = MessageBus()
    provider = AsyncMock()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        workspace = Path(tmp)
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace, model="test-model")

        configure_agent_orchestrator(loop)

        # Orchestrator is non-None
        assert loop._orchestrator is not None
        # Tools wired
        assert loop._orchestrator.tools is loop.tools
        # Current turn is None (not yet started)
        assert loop.current_turn is None


def test_configure_agent_orchestrator_prevents_fail_fast():
    """After configure_agent_orchestrator, _run_agent_loop does not raise."""
    from miqi.execution.factory import configure_agent_orchestrator
    from miqi.agent.loop import AgentLoop
    from miqi.bus.queue import MessageBus
    from pathlib import Path
    import asyncio
    import tempfile

    bus = MessageBus()
    provider = AsyncMock()
    provider.chat = AsyncMock()

    class FakeResponse:
        content = "Done"
        tool_calls = []
        reasoning_content = None
        usage = {}
        @property
        def has_tool_calls(self):
            return False
        @property
        def finish_reason(self):
            return "stop"

    provider.chat.return_value = FakeResponse()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        workspace = Path(tmp)
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace, model="test-model")

        configure_agent_orchestrator(loop)

        # This should NOT raise RuntimeError
        result = asyncio.run(loop._run_agent_loop(
            [{"role": "user", "content": "test"}],
            session_key="test:factory",
        ))
        assert result[0] is not None
