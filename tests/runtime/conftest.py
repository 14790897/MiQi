"""Fixtures specific to runtime tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def fake_services(fake_config, fake_provider):
    """Fake RuntimeServices for TaskRunner tests."""
    from miqi.runtime.services import RuntimeEventEmitter

    services = MagicMock()
    services.session_id = "test:session"
    services.workspace = fake_config.workspace_path
    services.provider = fake_provider
    services.event_emitter = RuntimeEventEmitter()
    services.agent_loop = MagicMock()
    services.agent_loop.process_direct = AsyncMock(return_value="hi there")
    services.agent_loop.stop = MagicMock()
    services.agent_loop.close_mcp = AsyncMock()
    services.tool_registry = MagicMock()
    services.orchestrator = MagicMock()
    services.agent_registry = MagicMock()
    services.agent_control = MagicMock()
    return services
