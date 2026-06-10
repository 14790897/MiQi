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
    """AbortTurn stops the agent loop."""
    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(AbortTurn(thread_id="cli:default"))

    fake_services.agent_loop.stop.assert_called_once()


@pytest.mark.asyncio
async def test_task_runner_emits_warning_for_unwired_types(fake_services):
    """ApprovalResponse emits a WARNING ErrorEvent (not wired in Phase 11)."""
    from miqi.protocol.commands import ApprovalResponse

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ApprovalResponse(approval_id="ap-1", decision="allow"))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert event.__class__.__name__ == "ErrorEvent"
    assert "not wired" in event.message


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
