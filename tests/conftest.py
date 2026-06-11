"""Shared fixtures for all test packages."""

import tempfile
from pathlib import Path

import pytest

from miqi.config.schema import Config


class _FakeResponse:
    """Minimal fake LLM response with all attributes AgentLoop accesses."""
    def __init__(self, content="done", tool_calls=None, finish_reason="stop"):
        self.content = content
        self.tool_calls = tool_calls or []
        self._has_tool_calls = bool(tool_calls)
        self.reasoning_content = None
        self.usage: dict[str, int] = {}
        self.finish_reason = finish_reason

    @property
    def has_tool_calls(self):
        return self._has_tool_calls


@pytest.fixture
def fake_config():
    """Minimal Config with all fields needed by AgentLoop constructor."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        config = Config()
        config.agents.defaults.workspace = str(tmp)
        yield config


@pytest.fixture
def fake_provider():
    """Fake LLM provider that returns canned responses."""
    class FakeProvider:
        def __init__(self):
            self.chat_calls: list[dict] = []

        async def chat(self, **kwargs):
            self.chat_calls.append(kwargs)
            return _FakeResponse(content="done", tool_calls=[])

        async def stream_chat(self, **kwargs):
            """Phase 20: streaming fallback wrapping chat()."""
            from miqi.providers.base import LLMStreamEvent
            response = await self.chat(**kwargs)
            yield LLMStreamEvent(kind="completed", response=response)

    return FakeProvider()
