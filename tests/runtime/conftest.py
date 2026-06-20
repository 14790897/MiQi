"""Fixtures specific to runtime tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_save_config(monkeypatch, tmp_path):
    """Prevent config tests from writing to real ~/.miqi/config.json.

    All tests that trigger config/batchWrite or config.update must go
    through this fixture, which redirects save_config to a tmp_path and
    patches the real loader's save_config to be a no-op.

    This fixture is autouse so every runtime test is protected.
    """
    import miqi.config.loader as loader_module

    # Redirect get_config_path to a temp location
    monkeypatch.setattr(loader_module, "get_config_path", lambda: tmp_path / "miqi" / "config.json")

    # Replace save_config with a safe wrapper that writes to tmp_path
    def _safe_save_config(config, config_path=None):
        path = config_path or (tmp_path / "miqi" / "config.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        data = config.model_dump(by_alias=True)
        with open(str(path), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    monkeypatch.setattr(loader_module, "save_config", _safe_save_config)
    yield
    # Restore happens automatically via monkeypatch


@pytest.fixture
def registry_with_state():
    """ClientSessionRegistry with a mock BridgeState in bridge_context.

    Phase 35 hardening: Handlers now read bridge state from
    registry.bridge_context instead of importing miqi.bridge.server.

    Returns (registry, mock_state) tuple.
    """
    from miqi.runtime.app_server import ClientSessionRegistry

    mock_state = MagicMock()
    registry = ClientSessionRegistry()
    registry.bridge_context = {"state": mock_state}
    return registry, mock_state


@pytest.fixture
def fake_services(fake_config, fake_provider):
    """Fake RuntimeServices for TaskRunner / TurnRunner tests."""
    from miqi.runtime.services import RuntimeEventEmitter, RuntimeModelSettings

    services = MagicMock()
    services.session_id = "test:session"
    services.workspace = fake_config.workspace_path
    services.provider = fake_provider
    services.event_emitter = RuntimeEventEmitter()
    services.model_settings = RuntimeModelSettings(
        model="test-model",
        temperature=0.1,
        max_tokens=4096,
        max_tool_result_chars=12000,
        context_limit_chars=600000,
    )
    services.tool_registry = MagicMock()
    services.tool_registry.get_definitions.return_value = []
    services.orchestrator = MagicMock()
    services.agent_registry = MagicMock()
    services.agent_control = MagicMock()
    # Phase 12 components
    services.tool_runtime = MagicMock()
    services.context_runtime = MagicMock()
    services.turn_runner = MagicMock()
    services.turn_runner.run = AsyncMock()
    run_result = MagicMock()
    run_result.final_content = "hi there"
    services.turn_runner.run.return_value = run_result
    # Phase 17: explicitly None to avoid MagicMock auto-creation
    services.history_runtime = None
    services.thread_runtime = None
    services.session_state = None
    # Phase 24: explicitly None to avoid MagicMock auto-creation
    services.ledger_runtime = None
    return services
