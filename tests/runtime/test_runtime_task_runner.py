"""Tests for TaskRunner (Phase 11.3)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.protocol.commands import UserMessage, AbortTurn
from miqi.runtime.task_runner import TaskRunner


@pytest.mark.asyncio
async def test_task_runner_routes_user_message_to_turn_runner(fake_services):
    """UserMessage goes through TurnRunner.run, not agent_loop.process_direct."""
    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(content="hello", thread_id="cli:default"))

    # TurnRunner is the new path
    fake_services.turn_runner.run.assert_awaited_once()
    # agent_loop.process_direct should NOT be called
    fake_services.agent_loop.process_direct.assert_not_awaited()

    # Phase 17: TurnStartedEvent is emitted before AgentMessageEvent.
    # Drain past non-content events until we find the final message.
    event = None
    while True:
        ev = await asyncio.wait_for(events.get(), timeout=1)
        if hasattr(ev, "content"):
            event = ev
            break
    assert event.content == "hi there"


@pytest.mark.asyncio
async def test_task_runner_handles_abort_turn(fake_services):
    """AbortTurn signals cancellation event and emits ErrorEvent (Phase 14 follow-up).

    No longer calls agent_loop.stop(). Instead sets the per-thread cancel
    event and emits an ErrorEvent warning.
    """
    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(AbortTurn(thread_id="cli:default"))

    # agent_loop.stop() is no longer called for abort
    fake_services.agent_loop.stop.assert_not_called()

    # Should emit an ErrorEvent (warning about abort)
    event = await asyncio.wait_for(events.get(), timeout=1)
    assert event.__class__.__name__ == "ErrorEvent"
    assert "aborted" in event.message.lower()


@pytest.mark.asyncio
async def test_approval_response_resolves_orchestrator(fake_services):
    """ApprovalResponse resolves the orchestrator's pending approval (Phase 18)."""
    from miqi.protocol.commands import ApprovalResponse
    from miqi.protocol.events import ApprovalResolvedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    seen: dict[str, str] = {}

    def resolve_approval(approval_id: str, decision: str) -> None:
        seen["approval_id"] = approval_id
        seen["decision"] = decision

    fake_services.orchestrator.resolve_approval = resolve_approval
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ApprovalResponse(approval_id="ap-1", decision="allow"))

    # Verify ApprovalResolvedEvent emitted
    event: object | None = None
    while True:
        ev = await asyncio.wait_for(events.get(), timeout=1)
        if isinstance(ev, ApprovalResolvedEvent):
            event = ev
            break

    assert event is not None, "Expected ApprovalResolvedEvent"
    assert event.approval_id == "ap-1"  # type: ignore[union-attr]
    assert event.decision == "allow"  # type: ignore[union-attr]
    assert seen == {"approval_id": "ap-1", "decision": "allow"}


@pytest.mark.asyncio
async def test_task_runner_emits_error_for_unknown_type(fake_services):
    """Unknown submission types get an ERROR ErrorEvent."""
    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    class BogusCommand:
        pass

    await runner.handle(BogusCommand())

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert event.__class__.__name__ == "ErrorEvent"
    assert "Unknown submission type" in event.message


# ---------------------------------------------------------------------------
# Phase 18: ThreadCommand wired to ThreadRuntime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thread_command_create_emits_thread_created(fake_services):
    """ThreadCommand(action='new') must call ThreadRuntime.create_thread
    and emit ThreadCreatedEvent."""
    from unittest.mock import AsyncMock

    from miqi.protocol.commands import ThreadCommand
    from miqi.protocol.events import ThreadCreatedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    thread = type("Thread", (), {
        "thread_id": "thread-new",
        "title": "New thread",
        "parent_thread_id": None,
    })()

    fake_services.thread_runtime = MagicMock()
    fake_services.thread_runtime.create_thread = AsyncMock(return_value=thread)
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ThreadCommand(
        action="new",
        thread_id="ignored",
        params={"title": "New thread"},
    ))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, ThreadCreatedEvent)
    assert event.thread_id == "thread-new"
    assert event.title == "New thread"


@pytest.mark.asyncio
async def test_thread_command_unknown_action_rejected(fake_services):
    """ThreadCommand with unknown action emits CommandRejectedEvent."""
    from miqi.protocol.commands import ThreadCommand
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.thread_runtime = MagicMock()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ThreadCommand(action="explode", thread_id="t1"))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert event.command_type == "ThreadCommand"


@pytest.mark.asyncio
async def test_task_runner_sanitizes_processing_errors(fake_services):
    """Exception messages from turn runner are sanitized, not leaked."""
    import asyncio as _asyncio

    # TurnRunner.run raises with sensitive details
    fake_services.turn_runner.run.side_effect = RuntimeError(
        "secret API key leaked in stack trace"
    )

    events = _asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    from miqi.protocol.commands import UserMessage
    await runner.handle(UserMessage(content="test", thread_id="cli:default"))

    # Phase 17: TurnStartedEvent arrives first, then ErrorEvent.
    # Drain past non-ErrorEvent events.
    event = None
    while True:
        ev = await _asyncio.wait_for(events.get(), timeout=1)
        if ev.__class__.__name__ == "ErrorEvent":
            event = ev
            break
    assert "secret API key" not in event.message
    assert "An internal error occurred" in event.message


# ---------------------------------------------------------------------------
# Phase 13: TaskRunner main path uses CapabilityResolver + PermissionProfile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_runner_attaches_capabilities_and_permission_profile(fake_services):
    """The main UserMessage path must resolve capabilities via CapabilityResolver
    and attach a PermissionProfile to the TurnContext before calling TurnRunner."""
    import asyncio as _asyncio
    from unittest.mock import MagicMock

    from miqi.runtime.capabilities import CapabilityResolver
    from miqi.runtime.task_runner import TaskRunner

    # Create a proper CapabilityResolver
    tool_reg = MagicMock()
    tool_reg.get_definitions.return_value = [
        {"type": "function", "function": {"name": "read_file", "parameters": {}}},
        {"type": "function", "function": {"name": "exec", "parameters": {}}},
    ]
    fake_services.tool_registry = tool_reg

    capability_resolver = CapabilityResolver(
        tool_registry=tool_reg,
        plugin_manager=None,
    )
    fake_services.capability_resolver = capability_resolver

    # Track what turn and tools TurnRunner receives
    captured_turn = None
    captured_tools = None

    async def _capture(**kwargs):
        nonlocal captured_turn, captured_tools
        captured_turn = kwargs.get("turn")
        captured_tools = kwargs.get("tools")
        run_result = MagicMock()
        run_result.final_content = "ok"
        return run_result

    fake_services.turn_runner.run.side_effect = _capture

    events = _asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    from miqi.protocol.commands import UserMessage
    await runner.handle(UserMessage(content="hello", thread_id="cli:default"))

    # TurnContext should have capabilities attached
    assert captured_turn is not None, "TurnRunner was not called"
    assert captured_turn.capabilities is not None, "turn.capabilities was not set"
    assert len(captured_turn.capabilities.tool_definitions) > 0, (
        "capabilities.tool_definitions should have tools"
    )

    # Tools passed to TurnRunner should come from capability resolver
    assert captured_tools is not None, "tools argument was not passed"
    assert len(captured_tools) > 0, "tools should come from capabilities"
    assert captured_tools == captured_turn.capabilities.tool_definitions

    # TurnContext should have permission_profile
    assert captured_turn.permission_profile is not None, (
        "turn.permission_profile was not set"
    )
    from miqi.runtime.permission_profile import PermissionProfile
    assert isinstance(captured_turn.permission_profile, PermissionProfile)
    assert captured_turn.permission_profile.workspace == fake_services.workspace

    # Phase 17: verify AgentMessageEvent was queued (after TurnStartedEvent)
    event = None
    while True:
        ev = await _asyncio.wait_for(events.get(), timeout=1)
        if hasattr(ev, "content"):
            event = ev
            break
    assert event.content == "ok"
