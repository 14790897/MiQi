"""Tests for TaskRunner (Phase 11.3)."""

import asyncio

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
    event = await asyncio.wait_for(events.get(), timeout=1)
    assert hasattr(event, "content")
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
async def test_task_runner_emits_warning_for_unwired_types(fake_services):
    """ApprovalResponse emits a WARNING ErrorEvent (not wired in Phase 11)."""
    from miqi.protocol.commands import ApprovalResponse

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ApprovalResponse(approval_id="ap-1", decision="allow"))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert event.__class__.__name__ == "ErrorEvent"
    assert "not yet wired" in event.message


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

    event = await _asyncio.wait_for(events.get(), timeout=1)
    assert event.__class__.__name__ == "ErrorEvent"
    # Must NOT leak the raw exception message
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

    # Verify an AgentMessageEvent was queued
    event = await _asyncio.wait_for(events.get(), timeout=1)
    assert event.content == "ok"
