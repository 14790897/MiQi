"""Tests for RuntimeClient (Phase 14.1)."""

import pytest

from miqi.protocol.commands import UserMessage
from miqi.protocol.events import AgentMessageEvent, ErrorEvent, EventSeverity
from miqi.runtime.client import RuntimeClient


class FakeRuntime:
    def __init__(self, events):
        self.submissions = []
        self.events = list(events)

    async def submit(self, submission):
        self.submissions.append(submission)

    async def next_event(self, timeout=None):
        if not self.events:
            return None
        return self.events.pop(0)


@pytest.mark.asyncio
async def test_runtime_client_returns_final_content():
    runtime = FakeRuntime([
        AgentMessageEvent(turn_id="t1", content="hello", finish_reason="stop")
    ])
    client = RuntimeClient(runtime)

    result = await client.ask("hi", thread_id="cli:default")

    assert result == "hello"
    assert isinstance(runtime.submissions[0], UserMessage)
    assert runtime.submissions[0].content == "hi"
    assert runtime.submissions[0].thread_id == "cli:default"


@pytest.mark.asyncio
async def test_runtime_client_forwards_progress_events():
    seen = []

    class ProgressEvent:
        turn_id = "t1"
        content = "working"

    runtime = FakeRuntime([
        ProgressEvent(),
        AgentMessageEvent(turn_id="t1", content="done", finish_reason="stop"),
    ])
    client = RuntimeClient(runtime)

    result = await client.ask("hi", thread_id="cli:default", on_event=seen.append)

    assert result == "done"
    assert seen and isinstance(seen[0], ProgressEvent)


@pytest.mark.asyncio
async def test_runtime_client_raises_on_error_event():
    runtime = FakeRuntime([
        ErrorEvent(
            turn_id="t1",
            severity=EventSeverity.ERROR,
            message="nope",
            recoverable=False,
        )
    ])
    client = RuntimeClient(runtime)

    with pytest.raises(RuntimeError, match="nope"):
        await client.ask("hi", thread_id="cli:default")


@pytest.mark.asyncio
async def test_runtime_client_times_out():
    runtime = FakeRuntime([])  # No events — will timeout
    client = RuntimeClient(runtime)

    with pytest.raises(TimeoutError, match="Timed out"):
        await client.ask("hi", thread_id="cli:default", timeout=0.01)
