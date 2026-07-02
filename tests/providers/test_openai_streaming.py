"""Tests for OpenAIProvider.stream_chat() fake-client streaming (Phase 20)."""

import pytest

from miqi.providers.base import LLMStreamEvent


# ── Fake OpenAI streaming chunk helpers ──────────────────────────────


class _FakeDelta:
    """Simulates an OpenAI streaming delta with optional content / reasoning."""
    def __init__(self, content="", reasoning_content="", tool_calls=None):
        self.content = content or None
        self.reasoning_content = reasoning_content or None
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, delta, finish_reason=None, index=0):
        self.delta = delta
        self.finish_reason = finish_reason
        self.index = index


class _FakeStream:
    """Async iterable that yields fake OpenAI completion chunks."""

    def __init__(self, choices_by_chunk: list[list[_FakeChoice]]):
        self._chunks = [
            type("Chunk", (), {"choices": choices})()
            for choices in choices_by_chunk
        ]

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


# ── Test helpers ────────────────────────────────────────────────────


async def _stream_events(provider, **kwargs) -> list[LLMStreamEvent]:
    """Collect all LLMStreamEvents from provider.stream_chat()."""
    events: list[LLMStreamEvent] = []
    async for event in provider.stream_chat(**kwargs):
        events.append(event)
    return events


# ── Tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openai_streaming_emits_content_deltas():
    """Content chunks become content_delta events; stream ends with completed."""
    from miqi.providers.openai_provider import OpenAIProvider

    chunks = [
        [_FakeChoice(_FakeDelta(content="hel"))],
        [_FakeChoice(_FakeDelta(content="lo"))],
        [_FakeChoice(_FakeDelta(), finish_reason="stop")],
    ]

    provider = OpenAIProvider(api_key="sk-test")
    # Replace the internal client's create — must be a coroutine function
    # so that `await client.chat.completions.create()` works.
    async def _fake_create(**kw):
        return _FakeStream(chunks)
    provider._client.chat.completions.create = _fake_create

    events = await _stream_events(
        provider,
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o",
    )

    kinds = [e.kind for e in events]
    assert kinds == ["content_delta", "content_delta", "completed"], (
        f"Expected content deltas then completed: {kinds}"
    )
    assert events[0].delta == "hel"
    assert events[1].delta == "lo"
    assert events[-1].response is not None
    assert events[-1].response.content == "hello"


@pytest.mark.asyncio
async def test_openai_streaming_yields_error_on_exception():
    """When the stream raises, a single completed event with error content
    is yielded so the runtime never hangs without a terminal event."""
    from miqi.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(api_key="sk-test")
    provider._client.chat.completions.create = lambda **kw: (
        __import__("builtins").exec("raise RuntimeError('connection reset')")
    )

    events = await _stream_events(
        provider,
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o",
    )

    assert len(events) == 1
    assert events[0].kind == "completed"
    assert events[0].response is not None
    assert events[0].response.finish_reason == "error"
    assert "unexpected error" in events[0].response.content.lower()


@pytest.mark.asyncio
async def test_openai_streaming_emits_reasoning_deltas():
    """Reasoning chunks become reasoning_delta events (Kimi, DeepSeek-R1)."""
    from miqi.providers.openai_provider import OpenAIProvider

    chunks = [
        [_FakeChoice(_FakeDelta(reasoning_content="Let me think"))],
        [_FakeChoice(_FakeDelta(reasoning_content=" about this"))],
        [_FakeChoice(_FakeDelta(content="answer"), finish_reason="stop")],
    ]

    provider = OpenAIProvider(api_key="sk-test")
    async def _fake_create(**kw):
        return _FakeStream(chunks)
    provider._client.chat.completions.create = _fake_create

    events = await _stream_events(
        provider,
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o",
    )

    kinds = [e.kind for e in events]
    assert "reasoning_delta" in kinds, f"Expected reasoning_delta in: {kinds}"
    assert "completed" in kinds

    reasoning_events = [e for e in events if e.kind == "reasoning_delta"]
    assert reasoning_events[0].delta == "Let me think"
    assert reasoning_events[1].delta == " about this"

    # Final content should still be in the completed response
    assert events[-1].response is not None
    assert events[-1].response.content == "answer"


# ── Issue #24: stream tool-call args need json_repair fallback ────────────


class _FakeFunction:
    """Simulates an OpenAI streaming tool-call function delta."""

    def __init__(self, name="", arguments=""):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    """Simulates an OpenAI streaming tool-call delta with an index."""

    def __init__(self, index=0, id="call_1", name="", arguments=""):
        self.index = index
        self.id = id
        self.type = "function"
        self.function = _FakeFunction(name=name, arguments=arguments)


async def _stream_with_tool_args(provider, arguments_str: str) -> list[LLMStreamEvent]:
    """Stream a single tool call whose accumulated arguments = arguments_str."""
    chunks = [
        [_FakeChoice(_FakeDelta(tool_calls=[_FakeToolCall(
            index=0, id="call_1", name="web_search", arguments=arguments_str,
        )]))],
        [_FakeChoice(_FakeDelta(), finish_reason="tool_calls")],
    ]

    async def _fake_create(**kw):
        return _FakeStream(chunks)

    provider._client.chat.completions.create = _fake_create
    return await _stream_events(
        provider,
        messages=[{"role": "user", "content": "search the news"}],
        model="gpt-4o",
    )


@pytest.mark.asyncio
async def test_stream_malformed_tool_args_repaired_not_dropped():
    """Issue #24: slightly malformed tool-call args must be repaired by
    json_repair (matching the non-stream path), not silently fall back to {}."""
    from miqi.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(api_key="sk-test")
    # Single-quoted JSON: json.loads fails, json_repair recovers the real args.
    events = await _stream_with_tool_args(provider, "{'query': '今日要闻'}")

    completed = events[-1]
    assert completed.kind == "completed"
    assert completed.response is not None
    assert len(completed.response.tool_calls) == 1
    args = completed.response.tool_calls[0].arguments
    # Must recover the real query, not silently become {}.
    assert args == {"query": "今日要闻"}, f"json_repair should recover args, got {args!r}"


@pytest.mark.asyncio
async def test_stream_valid_tool_args_unchanged():
    """Valid tool-call args parse as before (regression guard)."""
    from miqi.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(api_key="sk-test")
    events = await _stream_with_tool_args(provider, '{"query": "今日要闻"}')

    completed = events[-1]
    assert completed.response.tool_calls[0].arguments == {"query": "今日要闻"}


@pytest.mark.asyncio
async def test_stream_malformed_tool_args_logs_warning():
    """Issue #24: malformed args must also log a warning (parity with non-stream)."""
    from loguru import logger as loguru_logger

    from miqi.providers.openai_provider import OpenAIProvider

    messages: list[str] = []

    def _sink(message):
        messages.append(str(message.record["message"]))

    # loguru uses its own sinks (not stdlib logging), so capture via a test
    # sink instead of pytest's caplog.
    handler_id = loguru_logger.add(_sink, level="WARNING")
    try:
        provider = OpenAIProvider(api_key="sk-test")
        await _stream_with_tool_args(provider, "{'query': '今日要闻'}")
    finally:
        loguru_logger.remove(handler_id)

    assert any("malformed tool args" in m for m in messages), (
        f"expected a malformed-tool-args warning, got: {messages}"
    )
