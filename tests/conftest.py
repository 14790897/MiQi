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


@pytest.fixture(autouse=True)
def isolated_process_environment(monkeypatch, tmp_path, request):
    """Isolate every test from the real user home and system temp.

    Sets MIQI_HOME, HOME, USERPROFILE, TEMP, TMP, TMPDIR, and
    tempfile.tempdir below ``tmp_path`` so that no MiQi-owned write
    or third-party temp file can accidentally land in the real user
    profile.

    Tests decorated with ``@pytest.mark.self_managed_env`` opt out
    of automatic isolation — they MUST set all six environment
    variables themselves before any path access.
    """
    import tempfile

    if request.node.get_closest_marker("self_managed_env") is not None:
        return

    home = tmp_path / "home"
    miqi_home = tmp_path / ".miqi"
    temp_dir = tmp_path / "tmp"
    home.mkdir()
    temp_dir.mkdir()

    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("TEMP", str(temp_dir))
    monkeypatch.setenv("TMP", str(temp_dir))
    monkeypatch.setenv("TMPDIR", str(temp_dir))
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))
