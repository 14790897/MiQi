"""Tests for RuntimeServices and RuntimeSession (Phase 11)."""

import asyncio

import pytest

from miqi.protocol.commands import UserMessage
from miqi.runtime.services import RuntimeServices
from miqi.runtime.session import RuntimeSession


# ── Task 11.1: RuntimeServices ──────────────────────────────────────────

def test_runtime_services_builds_orchestrator(fake_config, fake_provider):
    """RuntimeServices.from_config creates all services with orchestrator wired."""
    services = RuntimeServices.from_config(
        config=fake_config,
        provider=fake_provider,
        session_id="test:session",
        workspace=fake_config.workspace_path,
    )

    assert services.provider is fake_provider
    assert services.tool_registry is not None
    assert services.orchestrator is not None
    assert services.orchestrator.tools is services.tool_registry
    assert services.event_emitter is not None
    assert services.agent_loop is not None
    assert services.agent_control is not None
    # AgentControl must have orchestrator wired
    assert services.agent_control._orchestrator is services.orchestrator


def test_runtime_services_wires_spawn_tool(fake_config, fake_provider):
    """SpawnTool._agent_control is wired by RuntimeServices."""
    services = RuntimeServices.from_config(
        config=fake_config,
        provider=fake_provider,
        session_id="test:session",
        workspace=fake_config.workspace_path,
    )

    spawn_tool = services.tool_registry.get("spawn")
    if spawn_tool is not None:
        assert hasattr(spawn_tool, "_agent_control")
        assert spawn_tool._agent_control is services.agent_control


# ── Task 11.2: RuntimeSession ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_runtime_session_accepts_user_message(fake_config, fake_provider):
    """RuntimeSession start → submit → next_event → stop flow."""
    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="cli:default",
        workspace=fake_config.workspace_path,
    )

    await runtime.start()
    await runtime.submit(UserMessage(content="hello", thread_id="cli:default"))
    event = await runtime.next_event(timeout=5)
    await runtime.stop()

    assert event is not None, "Expected an event from runtime"
    # AgentMessageEvent has 'content' attribute
    assert hasattr(event, "content"), f"Got {type(event).__name__}"
    assert event.content == "done"


@pytest.mark.asyncio
async def test_runtime_session_emits_error_on_bad_provider(fake_config):
    """RuntimeSession emits ErrorEvent when provider fails."""

    class BadProvider:
        async def chat(self, **kwargs):
            raise RuntimeError("provider crash")

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=BadProvider(),
        session_id="cli:default",
        workspace=fake_config.workspace_path,
    )

    await runtime.start()
    await runtime.submit(UserMessage(content="test", thread_id="cli:default"))

    found_error = False
    while True:
        event = await runtime.next_event(timeout=5)
        if event is None:
            break
        if event.__class__.__name__ == "ErrorEvent":
            found_error = True
            break

    await runtime.stop()
    assert found_error, "Expected an ErrorEvent when provider crashes"


@pytest.mark.asyncio
async def test_runtime_session_next_event_timeout(fake_config, fake_provider):
    """next_event(timeout=0.1) returns None when no events."""
    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="cli:default",
        workspace=fake_config.workspace_path,
    )

    await runtime.start()
    # Don't submit — no events should be available
    event = await runtime.next_event(timeout=0.01)
    await runtime.stop()

    assert event is None


@pytest.mark.asyncio
async def test_runtime_session_receives_service_events(fake_config, fake_provider):
    """Events emitted by services (not just TaskRunner) flow to next_event()."""
    from miqi.protocol.commands import UserMessage

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="cli:default",
        workspace=fake_config.workspace_path,
    )

    await runtime.start()

    # Inject an event through the services' event emitter directly,
    # simulating what the orchestrator or AgentControl would emit
    from miqi.protocol.events import ToolCallBeginEvent
    await runtime.services.event_emitter.emit(ToolCallBeginEvent(
        turn_id="test-turn",
        tool_call_id="tc-1",
        tool_name="read_file",
        tool_display="read_file /tmp/x",
        arguments={"path": "/tmp/x"},
    ))

    await runtime.submit(UserMessage(content="hello", thread_id="cli:default"))

    # The first event should be our manually-injected tool event
    first_event = await runtime.next_event(timeout=5)
    await runtime.stop()

    assert first_event is not None
    assert first_event.__class__.__name__ == "ToolCallBeginEvent"
    assert first_event.tool_name == "read_file"


# ---------------------------------------------------------------------------
# Phase 14 follow-up: abort cancellation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_session_abort_cancels_active_turn(fake_config):
    """Submitting AbortTurn after UserMessage must cancel the active turn
    and emit a cancellation event."""

    class BlockingProvider:
        async def chat(self, **kwargs):
            await asyncio.sleep(10)  # Blocks until cancelled
            return type("FakeResponse", (), {
                "content": "done", "tool_calls": [], "has_tool_calls": False,
            })()

    from miqi.protocol.commands import AbortTurn

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=BlockingProvider(),
        session_id="cli:default",
        workspace=fake_config.workspace_path,
    )

    await runtime.start()

    # Submit UserMessage (will block on provider.chat)
    await runtime.submit(UserMessage(content="long task", thread_id="cli:default"))

    # Give the turn a tick to enter provider.chat
    await asyncio.sleep(0.05)

    # Submit abort
    await runtime.submit(AbortTurn(thread_id="cli:default"))

    # Collect events — should see the abort warning, not a completed response
    events_seen: list[str] = []
    try:
        while True:
            event = await asyncio.wait_for(runtime.next_event(), timeout=2)
            events_seen.append(event.__class__.__name__)
            if "ErrorEvent" in events_seen or "AgentMessage" in events_seen:
                break
    except asyncio.TimeoutError:
        pass

    await runtime.stop()

    # Must have seen the abort-related event (either ErrorEvent from abort,
    # or the runtime should have cancelled)
    assert any(
        "Error" in e or "abort" in e.lower()
        for e in events_seen
    ), f"No abort event seen. Events: {events_seen}"

