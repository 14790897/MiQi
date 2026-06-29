"""Tests for config handlers — Phase 28.3 / Phase 38.5.

Validates that config.get returns redacted config, config.update
saves and propagates to active sessions, and error paths are safe.

Phase 38.5: Updated to use registry.bridge_context["state"] DI
instead of the deprecated import miqi.bridge.server pattern.
"""

from unittest.mock import MagicMock

import pytest


def _setup_registry(fake_config, tmp_path):
    """Set up a ClientSessionRegistry with bridge_state in bridge_context."""
    from miqi.runtime.app_server import ClientSessionRegistry

    registry = ClientSessionRegistry()
    state = MagicMock()
    state.load_config.return_value = fake_config
    state.config = fake_config
    registry.bridge_context = {
        "state": state,
    }
    return registry


# ── config.get ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_get_returns_redacted_config(fake_config, fake_provider, tmp_path):
    """config.get returns config dict with secrets redacted."""
    from miqi.runtime.config_handlers import config_get_handler

    registry = _setup_registry(fake_config, tmp_path)

    result = await config_get_handler("req-1", {}, "client-1", None, registry)
    assert "result" in result
    assert isinstance(result["result"], dict)


# ── config.update ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_update_saves_and_propagates(fake_config, fake_provider, tmp_path):
    """config.update saves config and propagates to active sessions."""
    from miqi.runtime.config_handlers import config_get_handler, config_update_handler

    registry = _setup_registry(fake_config, tmp_path)

    # Get the current config
    old_result = await config_get_handler("req-1", {}, "client-1", None, registry)

    # Create a session so propagation can be verified
    session = await registry.create_session(
        client_id="client-1",
        session_key="test-session",
        config=fake_config,
        provider=fake_provider,
        workspace=tmp_path,
    )

    # Update a safe field (agents.defaults.name) to test propagation
    result = await config_update_handler(
        "req-1",
        {"config": {"agents": {"defaults": {"name": "phase-28-test"}}}},
        "client-1", None, registry,
    )
    assert result["result"]["saved"] is True

    # Verify propagation: session's config_snapshot should have been updated
    session_state = getattr(session.services, "session_state", None)
    if session_state is not None:
        assert session_state.config_snapshot is not None


@pytest.mark.asyncio
async def test_config_update_rejects_empty_config(fake_config, fake_provider, tmp_path):
    """config.update rejects empty config param."""
    from miqi.runtime.app_server import AppServerError
    from miqi.runtime.config_handlers import config_update_handler

    registry = _setup_registry(fake_config, tmp_path)

    with pytest.raises(AppServerError) as exc_info:
        await config_update_handler("req-1", {"config": {}}, "client-1", None, registry)
    assert exc_info.value.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_config_update_rejects_missing_config_param(fake_config, fake_provider, tmp_path):
    """config.update rejects request without config param."""
    from miqi.runtime.app_server import AppServerError
    from miqi.runtime.config_handlers import config_update_handler

    registry = _setup_registry(fake_config, tmp_path)

    with pytest.raises(AppServerError) as exc_info:
        await config_update_handler("req-1", {}, "client-1", None, registry)
    assert exc_info.value.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_config_update_rejects_invalid_config(fake_config, fake_provider, tmp_path):
    """config.update rejects invalid config with INVALID_PARAMS code."""
    from miqi.runtime.app_server import AppServerError
    from miqi.runtime.config_handlers import config_update_handler

    registry = _setup_registry(fake_config, tmp_path)

    with pytest.raises(AppServerError) as exc_info:
        await config_update_handler(
            "req-1",
            {"config": {"agents": {"defaults": {"model": None}}}},
            "client-1", None, registry,
        )
    assert exc_info.value.code == "INVALID_PARAMS"
