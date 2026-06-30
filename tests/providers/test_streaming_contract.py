"""Tests for LLMProvider streaming fallback contract (Phase 20)."""

import pytest

from miqi.providers.base import LLMProvider, LLMResponse, LLMStreamEvent


class FakeProvider(LLMProvider):
    """Concrete provider that returns a simple chat response."""

    async def chat(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
    ):
        return LLMResponse(content="final", finish_reason="stop")

    def get_default_model(self) -> str:
        return "test-model"


@pytest.mark.asyncio
async def test_default_stream_chat_wraps_chat_response():
    """The default stream_chat() must call chat() and yield a single
    LLMStreamEvent of kind 'completed' wrapping the LLMResponse."""
    provider = FakeProvider()

    events = [
        event
        async for event in provider.stream_chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            model="test-model",
            temperature=0.1,
            max_tokens=100,
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0], LLMStreamEvent)
    assert events[0].kind == "completed"
    assert events[0].response is not None
    assert events[0].response.content == "final"
