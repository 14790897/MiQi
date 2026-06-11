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


# ---------------------------------------------------------------------------
# Phase 14 follow-up: concurrency safety
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_client_concurrent_asks_dont_interleave():
    """Two concurrent ask() on the same client must not mix up responses."""
    import asyncio as _asyncio

    class QueuedRuntime:
        """Runtime that queues responses deterministically."""
        def __init__(self):
            self.submissions = []
            self._events: _asyncio.Queue = _asyncio.Queue()

        async def submit(self, submission):
            self.submissions.append(submission)

        async def next_event(self, timeout=None):
            try:
                return await _asyncio.wait_for(self._events.get(), timeout=timeout or 5)
            except _asyncio.TimeoutError:
                return None

    runtime = QueuedRuntime()
    client = RuntimeClient(runtime)

    # Queue events for two users: "A" first, then "B"
    await runtime._events.put(AgentMessageEvent(turn_id="tA", content="response-A", finish_reason="stop"))
    await runtime._events.put(AgentMessageEvent(turn_id="tB", content="response-B", finish_reason="stop"))

    async def ask_a():
        return await client.ask("msg-A", thread_id="thread-A")

    async def ask_b():
        return await client.ask("msg-B", thread_id="thread-B")

    ra, rb = await _asyncio.gather(ask_a(), ask_b())

    # Each must get its OWN response (not swapped)
    assert ra == "response-A", f"A got {ra}"
    assert rb == "response-B", f"B got {rb}"
    assert len(runtime.submissions) == 2


# ---------------------------------------------------------------------------
# Phase 14 follow-up v2: per-runtime lock (two clients, one runtime)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_client_per_runtime_lock_two_clients():
    """Two different RuntimeClient instances sharing one RuntimeSession
    must not interleave responses. The lock is on the runtime."""
    import asyncio as _asyncio

    class QueuedRuntime:
        def __init__(self):
            self.submissions = []
            self._events: _asyncio.Queue = _asyncio.Queue()
            self._ask_lock = _asyncio.Lock()

        async def submit(self, submission):
            self.submissions.append(submission)

        async def next_event(self, timeout=None):
            try:
                return await _asyncio.wait_for(self._events.get(), timeout=timeout or 5)
            except _asyncio.TimeoutError:
                return None

    runtime = QueuedRuntime()
    client_a = RuntimeClient(runtime)
    client_b = RuntimeClient(runtime)

    # Queue two responses
    await runtime._events.put(AgentMessageEvent(turn_id="tA", content="resp-A", finish_reason="stop"))
    await runtime._events.put(AgentMessageEvent(turn_id="tB", content="resp-B", finish_reason="stop"))

    async def ask_a():
        return await client_a.ask("msg-A", thread_id="thread-A")

    async def ask_b():
        return await client_b.ask("msg-B", thread_id="thread-B")

    ra, rb = await _asyncio.gather(ask_a(), ask_b())

    assert ra == "resp-A", f"Client A got wrong response: {ra}"
    assert rb == "resp-B", f"Client B got wrong response: {rb}"
    assert len(runtime.submissions) == 2
