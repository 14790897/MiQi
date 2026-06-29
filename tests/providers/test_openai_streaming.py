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
