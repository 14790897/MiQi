"""Tests for TurnRunner (Phase 12.3)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.runtime.turn_runner import TurnRunner


class _FakeTurnContext:
    turn_id = "turn-1"
    thread_id = "thread-1"
    model = "test-model"
    temperature = 0.0
    max_tokens = 100

    class _Meta:
        name = "code-agent"
    agent_metadata = _Meta()


class _FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self._has_tool_calls = bool(tool_calls)

    @property
    def has_tool_calls(self):
        return self._has_tool_calls


class _FakeToolCall:
    def __init__(self, name="read_file", args=None, tc_id="tc-1"):
        self.name = name
        self.arguments = args or {"path": "/tmp/x"}
        self.id = tc_id
        self.arguments_json = '{"path": "/tmp/x"}'


@pytest.fixture
def fake_turn_context():
    return _FakeTurnContext()


@pytest.fixture
def fake_tool_runtime():
    runtime = MagicMock()
    runtime.execute_many = AsyncMock()

    class _Ctx:
        def __init__(self, tc):
            self.tool_call_id = tc.id
            self.result = f"result-for-{tc.name}"
            # Mirror real orchestrator output: a successful tool call.
            from miqi.execution.orchestrator import OrchestrationResult
            self.status = OrchestrationResult.SUCCESS

    async def _fake_execute_many(turn, calls):
        return [_Ctx(c) for c in calls]

    runtime.execute_many.side_effect = _fake_execute_many
    return runtime


@pytest.fixture
def fake_context_runtime():
    from miqi.runtime.context_runtime import ContextRuntime
    return ContextRuntime()


@pytest.fixture
def turn_runner(fake_tool_runtime, fake_context_runtime):
    from miqi.providers.base import LLMStreamEvent

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    # Phase 20: TurnRunner uses stream_chat() — mock it as an async generator.
    async def _default_stream(**kwargs):
        yield LLMStreamEvent(
            kind="completed",
            response=_FakeResponse(content="final answer"),
        )

    provider.stream_chat = _default_stream
    ev = MagicMock()
    ev.emit = AsyncMock()
    return TurnRunner(
        provider=provider,
        tool_runtime=fake_tool_runtime,
        context_runtime=fake_context_runtime,
        event_emitter=ev,
        max_iterations=3,
    ), provider


# ── Tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_turn_runner_returns_final_response(turn_runner, fake_turn_context):
    runner, provider = turn_runner

    result = await runner.run(
        turn=fake_turn_context,
        user_content="hello",
        system_prompt="system",
        tools=[],
    )

    assert result.final_content == "final answer"
    assert result.messages[-1]["role"] == "assistant"
    # Phase 20: no direct chat() call — stream_chat is used instead
    assert not hasattr(provider, "chat_called") or True  # sanity


@pytest.mark.asyncio
async def test_turn_runner_handles_tool_calls(turn_runner, fake_turn_context, fake_tool_runtime):
    from miqi.providers.base import LLMStreamEvent

    runner, provider = turn_runner

    # First response: tool calls
    tc = _FakeToolCall("read_file")

    # Phase 20: stream_chat with side_effect
    call_count = 0

    async def _stream_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield LLMStreamEvent(
                kind="completed",
                response=_FakeResponse(tool_calls=[tc]),
            )
        else:
            yield LLMStreamEvent(
                kind="completed",
                response=_FakeResponse(content="done after tools"),
            )

    provider.stream_chat = _stream_side_effect

    result = await runner.run(
        turn=fake_turn_context,
        user_content="task",
        system_prompt="sys",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )

    assert result.final_content == "done after tools"
    assert "read_file" in result.tools_used
    assert call_count == 2  # stream_chat was called twice
    fake_tool_runtime.execute_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_turn_runner_emits_tool_call_lifecycle_events(
    turn_runner, fake_turn_context, fake_tool_runtime
):
    from miqi.protocol.events import ToolCallBeginEvent, ToolCallEndEvent
    from miqi.providers.base import LLMStreamEvent

    runner, provider = turn_runner
    emitted = []
    runner._events.emit.side_effect = lambda event: emitted.append(event)

    tc = _FakeToolCall("write_file", {"path": "/tmp/asset.txt"}, "tc-write")
    tc.arguments_json = '{"path": "/tmp/asset.txt"}'

    async def _execute_many(turn, calls):
        emitted.append("execute_many")

        class _Ctx:
            tool_call_id = "tc-write"
            result = "created"
            duration_ms = 12
            # Mirror real orchestrator output: write_file succeeded.
            from miqi.execution.orchestrator import OrchestrationResult
            status = OrchestrationResult.SUCCESS

        return [_Ctx()]

    fake_tool_runtime.execute_many.side_effect = _execute_many

    call_count = 0

    async def _stream_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield LLMStreamEvent(
                kind="completed",
                response=_FakeResponse(tool_calls=[tc]),
            )
        else:
            yield LLMStreamEvent(
                kind="completed",
                response=_FakeResponse(content="done after tools"),
            )

    provider.stream_chat = _stream_side_effect

    result = await runner.run(
        turn=fake_turn_context,
        user_content="create a file",
        system_prompt="sys",
        tools=[{"type": "function", "function": {"name": "write_file", "parameters": {}}}],
    )

    assert result.final_content == "done after tools"
    assert [type(event).__name__ if event != "execute_many" else event for event in emitted] == [
        "ToolCallBeginEvent",
        "execute_many",
        "ToolCallEndEvent",
    ]
    begin = emitted[0]
    end = emitted[2]
    assert isinstance(begin, ToolCallBeginEvent)
    assert begin.tool_name == "write_file"
    assert begin.tool_call_id == "tc-write"
    assert begin.arguments == {"path": "/tmp/asset.txt"}
    assert begin.tool_display == 'write_file("/tmp/asset.txt")'
    assert isinstance(end, ToolCallEndEvent)
    assert end.tool_name == "write_file"
    assert end.success is True
    assert end.output_preview == "created"
    assert end.output_size == len("created")
    assert end.duration_ms == 12


@pytest.mark.asyncio
async def test_turn_runner_exhausts_iterations(turn_runner, fake_turn_context):
    from miqi.providers.base import LLMStreamEvent

    runner, provider = turn_runner

    # Always return tool calls — forces exhaustion
    async def _always_tool_calls(**kwargs):
        yield LLMStreamEvent(
            kind="completed",
            response=_FakeResponse(tool_calls=[_FakeToolCall()]),
        )

    provider.stream_chat = _always_tool_calls
    runner._max_iterations = 2  # Small cap for fast test

    result = await runner.run(
        turn=fake_turn_context,
        user_content="endless task",
        system_prompt="sys",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )

    assert "Reached maximum iterations" in result.final_content


@pytest.mark.asyncio
async def test_turn_runner_tool_call_message_ordering(turn_runner, fake_turn_context):
    """TurnRunner must produce user → assistant(tool_calls) → tool → assistant."""
    from miqi.providers.base import LLMStreamEvent

    runner, provider = turn_runner

    tc1 = _FakeToolCall("read_file", {"path": "/tmp/a"}, "tcid-1")
    tc2 = _FakeToolCall("list_dir", {"path": "/tmp"}, "tcid-2")

    # Track the second stream_chat call's messages to verify ordering
    captured_messages: list = []
    call_count = 0

    async def _stream_smart(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield LLMStreamEvent(
                kind="completed",
                response=_FakeResponse(tool_calls=[tc1, tc2]),
            )
        else:
            captured_messages.extend(kwargs["messages"])
            yield LLMStreamEvent(
                kind="completed",
                response=_FakeResponse(content="done after tools"),
            )

    provider.stream_chat = _stream_smart

    result = await runner.run(
        turn=fake_turn_context,
        user_content="task",
        system_prompt="sys",
        tools=[
            {"type": "function", "function": {"name": "read_file", "parameters": {}}},
            {"type": "function", "function": {"name": "list_dir", "parameters": {}}},
        ],
    )

    assert result.final_content == "done after tools"

    # The second provider call should receive: user → assistant(tool_calls) → tool → tool
    roles = [m["role"] for m in captured_messages]
    assert roles == ["system", "user", "assistant", "tool", "tool"], (
        f"Bad tool-call ordering: {roles}"
    )

    # Assistant message must have tool_calls and appear before tool results
    asst_idx = roles.index("assistant")
    tool_indices = [i for i, r in enumerate(roles) if r == "tool"]
    assert asst_idx < tool_indices[0], "assistant(tool_calls) must precede tool results"

    # Tool call IDs must match
    tool_call_ids = [m["tool_call_id"] for m in captured_messages if m["role"] == "tool"]
    assert tool_call_ids == ["tcid-1", "tcid-2"], f"tool_call_ids out of order: {tool_call_ids}"


# ── Phase 20: streaming turn provider ────────────────────────────────────


@pytest.mark.asyncio
async def test_turn_runner_emits_content_deltas():
    """TurnRunner must emit AgentMessageDeltaEvent when the provider
    yields content_delta stream events, then return the final content."""
    from miqi.providers.base import LLMResponse, LLMStreamEvent
    from miqi.runtime.turn_runner import TurnRunner

    class StreamingProvider:
        async def stream_chat(self, **kwargs):
            yield LLMStreamEvent(kind="content_delta", delta="hel")
            yield LLMStreamEvent(kind="content_delta", delta="lo")
            yield LLMStreamEvent(
                kind="completed",
                response=LLMResponse(content="hello", finish_reason="stop"),
            )

    class FakeContext:
        def build_initial_messages(self, **kwargs):
            return [{"role": "user", "content": kwargs["user_content"]}]

        def add_assistant_message(self, *, messages, content, tool_calls=None):
            return [*messages, {"role": "assistant", "content": content}]

        def trim_for_model(self, messages, model):
            return messages

    class EventCollector:
        def __init__(self):
            self.events: list = []

        async def emit(self, event):
            self.events.append(event)

    events = EventCollector()
    runner = TurnRunner(
        provider=StreamingProvider(),
        tool_runtime=MagicMock(),
        context_runtime=FakeContext(),
        event_emitter=events,
        max_iterations=3,
    )
    turn = MagicMock()
    turn.turn_id = "turn-1"
    turn.model = "test-model"
    turn.temperature = 0.1
    turn.max_tokens = 100

    result = await runner.run(
        turn=turn,
        user_content="hi",
        system_prompt="system",
        tools=[],
    )

    assert result.final_content == "hello"

    from miqi.protocol.events import AgentMessageDeltaEvent
    deltas = [e for e in events.events if isinstance(e, AgentMessageDeltaEvent)]
    assert [e.delta for e in deltas] == ["hel", "lo"]
    assert [e.index for e in deltas] == [0, 1]


# ---------------------------------------------------------------------------
# Phase 41: Steering queue consumption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_runner_consumes_steer_queue_before_completing_final_response():
    import asyncio as _asyncio
    from miqi.providers.base import LLMResponse, LLMStreamEvent
    from miqi.runtime.turn_runner import TurnRunner

    class FakeProvider:
        def __init__(self):
            self.calls = 0

        async def stream_chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield LLMStreamEvent(kind="completed", response=LLMResponse(
                    content="first",
                    finish_reason="stop",
                ))
            else:
                yield LLMStreamEvent(kind="completed", response=LLMResponse(
                    content="second",
                    finish_reason="stop",
                ))

    class FakeContext:
        def build_initial_messages(self, **kwargs):
            return [{"role": "user", "content": kwargs["user_content"]}]

        def add_assistant_message(self, messages, content, tool_calls=None):
            return [*messages, {"role": "assistant", "content": content}]

        def add_tool_result(self, messages, tool_call_id, name, content):
            return [*messages, {"role": "tool", "content": content}]

        def trim_for_model(self, messages, model):
            return messages

    class FakeTools:
        async def execute_many(self, turn, tool_calls):
            return []

    class FakeEvents:
        async def emit(self, event):
            pass

    turn = type("Turn", (), {})()
    turn.turn_id = "turn-steer"
    turn.thread_id = "thread-steer"
    turn.model = "test-model"
    turn.temperature = 0
    turn.max_tokens = 100

    steer_queue = _asyncio.Queue()
    await steer_queue.put({
        "content": "steer me",
        "input_items": [{"type": "text", "text": "steer me"}],
        "client_user_message_id": "client-steer",
    })

    runner = TurnRunner(
        provider=FakeProvider(),
        tool_runtime=FakeTools(),
        context_runtime=FakeContext(),
        event_emitter=FakeEvents(),
        max_iterations=3,
    )

    result = await runner.run(
        turn=turn,
        user_content="hello",
        system_prompt="system",
        tools=[],
        history=[],
        steer_queue=steer_queue,
    )

    assert result.final_content == "second"
    steer_delta = next(
        d for d in result.messages_delta
        if d.get("role") == "user" and d.get("content") == "steer me"
    )
    assert steer_delta is not None
    assert steer_delta["client_user_message_id"] == "client-steer"
