"""Tests for TUI runtime connection (Phase 10).

Tests that TUI uses shared provider factory and creates orchestrator.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Task 10.7: TUI uses shared provider factory (not LLMProvider.from_config)
# ---------------------------------------------------------------------------

def test_tui_load_runtime_from_config_calls_make_provider():
    """_load_runtime_from_config must use the shared factory, not LLMProvider.from_config."""
    from miqi.tui.app import _load_runtime_from_config

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)

        # Create a minimal config file
        (workspace / ".miqi").mkdir(exist_ok=True)
        config_path = workspace / ".miqi" / "config.yaml"
        config_path.write_text("""
agents:
  defaults:
    model: gpt-4
    name: test-agent
    temperature: 0.1
    max_tokens: 4096
providers:
  openai:
    api_key: test-key
    api_base: https://api.openai.com/v1
workspace: {}
workspace_path: {}
""".format(str(workspace), str(workspace)))

        with patch("miqi.tui.app.Path.cwd", return_value=workspace):
            # Patch at the source modules since _load_runtime_from_config
            # uses 'from miqi.config.loader import load_config'
            with patch("miqi.config.loader.load_config") as mock_load:
                with patch("miqi.providers.factory.make_provider") as mock_make:
                    # Set up mocks
                    mock_config = MagicMock()
                    mock_config.agents.defaults.model = "gpt-4"
                    mock_load.return_value = mock_config
                    mock_provider = MagicMock()
                    mock_make.return_value = mock_provider

                    result = _load_runtime_from_config()

                    # make_provider was called with config
                    mock_make.assert_called_once_with(mock_config)
                    # Result is (provider, workspace, model)
                    assert result is not None
                    provider, ws, model = result
                    assert provider is mock_provider
                    assert model == "gpt-4"


def test_tui_load_runtime_handles_failure_gracefully():
    """_load_runtime_from_config returns None on failure (no crash)."""
    from miqi.tui.app import _load_runtime_from_config

    with patch("miqi.config.loader.load_config", side_effect=Exception("Config not found")):
        result = _load_runtime_from_config()
        assert result is None


# ---------------------------------------------------------------------------
# Task 10.8: TUI AgentLoop gets an orchestrator
# ---------------------------------------------------------------------------

def test_tui_connect_runtime_creates_orchestrator():
    """connect_runtime() must create orchestrator and wire it to AgentLoop."""
    from miqi.tui.app import MiQiTui
    import asyncio

    async def _test():
        app = MiQiTui(driver_class=None)  # Skip Textual driver for testing
        # Mock _append_message to avoid Textual DOM errors
        app._append_message = MagicMock()
        provider = AsyncMock()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            workspace = Path(tmp)
            await app.connect_runtime(provider, workspace)

            # AgentLoop was created
            assert app._agent_loop is not None

            # Orchestrator is set
            assert app._agent_loop._orchestrator is not None

            # Orchestrator.tools == AgentLoop.tools
            assert app._agent_loop._orchestrator.tools is app._agent_loop.tools

            # current_turn is None until processing starts
            assert app._agent_loop.current_turn is None

    asyncio.run(_test())


def test_tui_connect_runtime_agent_loop_would_fail_fast_without_orchestrator():
    """Without orchestrator, AgentLoop._run_agent_loop raises RuntimeError."""
    from miqi.agent.loop import AgentLoop
    from miqi.bus.queue import MessageBus

    bus = MessageBus()
    provider = AsyncMock()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        workspace = Path(tmp)
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace)
        # No orchestrator — should fail fast
        loop._orchestrator = None

        import pytest
        with pytest.raises(RuntimeError, match="ToolOrchestrator must be configured"):
            asyncio.run(loop._run_agent_loop(
                [{"role": "user", "content": "test"}],
                session_key="test:fail-fast",
            ))
