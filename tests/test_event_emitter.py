"""Tests for miqi.bridge.event_emitter."""

import pytest
from miqi.bridge.event_emitter import EventEmitter
from miqi.protocol.events import (
    TurnStartedEvent,
    AgentMessageDeltaEvent,
    ToolCallBeginEvent,
    ApprovalRequestedEvent,
    ErrorEvent,
    EventSeverity,
)


@pytest.fixture
def captured_events():
    """Capture emitted events for verification."""
    events = []

    def capture(channel, data):
        events.append((channel, data))

    return events, capture


@pytest.fixture
def emitter(captured_events):
    events, send = captured_events
    return EventEmitter(send)


@pytest.mark.asyncio
async def test_emit_turn_started(emitter, captured_events):
    events, _ = captured_events
    event = TurnStartedEvent(
        turn_id="turn_001",
        agent_name="main",
        thread_id="thread_abc",
    )
    await emitter.emit(event)
    assert len(events) == 1
    channel, data = events[0]
    assert channel == "turn:started"
    assert data["turn_id"] == "turn_001"


@pytest.mark.asyncio
async def test_emit_agent_message_delta(emitter, captured_events):
    events, _ = captured_events
    event = AgentMessageDeltaEvent(
        turn_id="turn_001",
        delta="Hello",
        index=0,
    )
    await emitter.emit(event)
    channel, data = events[0]
    assert channel == "chat:delta"
    assert data["delta"] == "Hello"


@pytest.mark.asyncio
async def test_emit_approval_requested(emitter, captured_events):
    events, _ = captured_events
    event = ApprovalRequestedEvent(
        approval_id="appr_001",
        turn_id="turn_001",
        category="exec",
        description="Run: rm -rf /tmp",
        allow_permanent=True,
    )
    await emitter.emit(event)
    channel, data = events[0]
    assert channel == "approval:request"
    assert data["approval_id"] == "appr_001"


@pytest.mark.asyncio
async def test_emit_error(emitter, captured_events):
    events, _ = captured_events
    event = ErrorEvent(
        turn_id="turn_001",
        severity=EventSeverity.ERROR,
        message="Something went wrong",
    )
    await emitter.emit(event)
    channel, data = events[0]
    assert channel == "chat:error"
    assert data["message"] == "Something went wrong"


@pytest.mark.asyncio
async def test_unknown_event_not_forwarded(emitter, captured_events):
    """Events without a type attribute should not cause errors."""
    events, _ = captured_events

    class UnknownEvent:
        pass

    await emitter.emit(UnknownEvent())
    assert len(events) == 0  # Unknown events silently dropped


@pytest.mark.asyncio
async def test_internal_events_not_forwarded(emitter, captured_events):
    """Internal events (context_compacted, session_configured) are not forwarded."""
    events, _ = captured_events
    from miqi.protocol.events import ContextCompactedEvent

    event = ContextCompactedEvent(
        turn_id="turn_001",
        thread_id="thread_abc",
        messages_before=100,
        messages_after=50,
        tokens_saved=5000,
    )
    await emitter.emit(event)
    assert len(events) == 0  # Internal events silently dropped
