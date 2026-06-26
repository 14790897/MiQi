"""Phase 10 tests — KUN runtime integration with gateway/CLI path."""

from __future__ import annotations

from pathlib import Path

import pytest

from miqi.kun_runtime.migration_adapter import (
    GatewayKunRuntime,
    session_key_to_thread_id,
)

# ═══════════════════════════════════════════════════════════════════════════════
# GatewayKunRuntime integration tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGatewayKunRuntime:
    @pytest.mark.asyncio
    async def test_process_direct_text_response(self, tmp_path: Path) -> None:
        """GatewayKunRuntime.process_direct() should return assistant text."""
        from miqi.agent.tools.filesystem import ReadFileTool
        from miqi.agent.tools.registry import ToolRegistry
        from miqi.agent.tools.shell import ExecTool

        # Build tool registry
        registry = ToolRegistry()
        registry.register(ReadFileTool(workspace=tmp_path / "ws"))
        registry.register(ExecTool(working_dir=str(tmp_path / "ws")))

        # Fake provider
        provider = _FakeProvider(content="Hello from KUN gateway!")

        gw = GatewayKunRuntime(
            data_dir=tmp_path / "kun_data",
            workspace=tmp_path / "ws",
            provider=provider,
            tool_registry=registry,
            model="fake-model",
            agent_name="test-gateway",
        )

        result = await gw.process_direct("Hello?", session_key="cli:test")
        assert "Hello from KUN gateway" in result

    @pytest.mark.asyncio
    async def test_process_direct_creates_thread(self, tmp_path: Path) -> None:
        """First call should create a thread and persist it."""
        from miqi.agent.tools.filesystem import ReadFileTool
        from miqi.agent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register(ReadFileTool(workspace=tmp_path / "ws"))

        provider = _FakeProvider(content="Response")

        gw = GatewayKunRuntime(
            data_dir=tmp_path / "kun_data",
            workspace=tmp_path / "ws",
            provider=provider,
            tool_registry=registry,
            model="fake-model",
        )

        await gw.process_direct("msg1", session_key="cli:persistent")
        thread_id = session_key_to_thread_id("cli:persistent")

        # Thread should exist in store
        thread = await gw._runtime.threads.get(thread_id)
        assert thread is not None
        assert thread["title"] == "cli:persistent"

    @pytest.mark.asyncio
    async def test_process_direct_reuses_thread(self, tmp_path: Path) -> None:
        """Same session_key should reuse the same thread."""
        from miqi.agent.tools.filesystem import ReadFileTool
        from miqi.agent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register(ReadFileTool(workspace=tmp_path / "ws"))

        provider = _FakeProvider(content="Response")

        gw = GatewayKunRuntime(
            data_dir=tmp_path / "kun_data",
            workspace=tmp_path / "ws",
            provider=provider,
            tool_registry=registry,
            model="fake-model",
        )

        await gw.process_direct("turn 1", session_key="cli:reuse")
        turns_before = await gw._runtime.threads.list()

        await gw.process_direct("turn 2", session_key="cli:reuse")
        turns_after = await gw._runtime.threads.list()

        # Thread count should not grow (reused)
        assert len(turns_after) == len(turns_before)

    @pytest.mark.asyncio
    async def test_process_direct_records_items(self, tmp_path: Path) -> None:
        """Items should be persisted in the session store."""
        from miqi.agent.tools.filesystem import ReadFileTool
        from miqi.agent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register(ReadFileTool(workspace=tmp_path / "ws"))

        provider = _FakeProvider(content="Done")

        gw = GatewayKunRuntime(
            data_dir=tmp_path / "kun_data",
            workspace=tmp_path / "ws",
            provider=provider,
            tool_registry=registry,
            model="fake-model",
        )

        await gw.process_direct("Do it", session_key="cli:items")
        thread_id = session_key_to_thread_id("cli:items")
        items = await gw._runtime.session_store.load_items(thread_id)

        kinds = [i["kind"] for i in items]
        assert "user_message" in kinds
        assert "assistant_text" in kinds

    @pytest.mark.asyncio
    async def test_stop_and_running_properties(self, tmp_path: Path) -> None:
        """GatewayKunRuntime should have stop/run compatibility methods."""
        from miqi.agent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        provider = _FakeProvider(content="OK")

        gw = GatewayKunRuntime(
            data_dir=tmp_path / "kun_data",
            workspace=tmp_path / "ws",
            provider=provider,
            tool_registry=registry,
            model="fake-model",
        )

        assert not gw._running
        await gw.run()
        assert gw._running
        gw.stop()
        assert not gw._running


# ═══════════════════════════════════════════════════════════════════════════════
# Config schema test
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfigRuntimeField:
    def test_default_is_legacy(self) -> None:
        from miqi.config.schema import AgentDefaults
        defaults = AgentDefaults()
        assert defaults.runtime == "legacy"

    def test_accepts_kun(self) -> None:
        from miqi.config.schema import AgentDefaults
        defaults = AgentDefaults(runtime="kun")
        assert defaults.runtime == "kun"

    def test_serialized_in_config(self) -> None:
        import json

        from miqi.config.schema import AgentsConfig
        cfg = AgentsConfig()
        raw = cfg.model_dump_json(by_alias=True)
        parsed = json.loads(raw)
        assert "runtime" in parsed["defaults"]
        assert parsed["defaults"]["runtime"] == "legacy"


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeProvider:
    """A minimal provider for testing GatewayKunRuntime without real API calls."""

    def __init__(self, content: str = "", tool_calls: list | None = None):
        self._content = content
        self._tool_calls = tool_calls or []

    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):
        from miqi.providers.base import LLMResponse, ToolCallRequest
        return LLMResponse(
            content=self._content,
            tool_calls=[ToolCallRequest(**tc) for tc in self._tool_calls],
            finish_reason="tool_calls" if self._tool_calls else "stop",
        )

    def get_default_model(self) -> str:
        return "fake-model"
