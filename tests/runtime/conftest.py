"""Fixtures specific to runtime tests."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


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
    from miqi.runtime.services import RuntimeEventEmitter

    services = MagicMock()
    services.session_id = "test:session"
    services.workspace = fake_config.workspace_path
    services.provider = fake_provider
    services.event_emitter = RuntimeEventEmitter()
    services.agent_loop = MagicMock()
    services.agent_loop.model = "test-model"
    services.agent_loop.temperature = 0.1
    services.agent_loop.max_tokens = 4096
    services.agent_loop.stop = MagicMock()
    services.agent_loop.close_mcp = AsyncMock()
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
