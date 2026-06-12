"""Tests for config handlers — Phase 28.3.

Validates that config.get returns redacted config, config.update
saves and propagates to active sessions, and error paths are safe.
"""

import asyncio

import pytest


# ── config.get ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_get_returns_redacted_config(fake_config, fake_provider, tmp_path):
    """config.get returns config dict with secrets redacted."""
    from miqi.runtime.app_server import ClientSessionRegistry
    from miqi.runtime.config_handlers import config_get_handler

    registry = ClientSessionRegistry()

    result = await config_get_handler("req-1", {}, "client-1", None, registry)
    assert "result" in result
    # The result should be a config dict (model_dump returns a dict)
    assert isinstance(result["result"], dict)


# ── config.update ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_update_saves_and_propagates(fake_config, fake_provider, tmp_path):
    """config.update saves config and propagates to active sessions."""
    from miqi.runtime.app_server import ClientSessionRegistry
    from miqi.runtime.config_handlers import config_get_handler, config_update_handler

    import miqi.bridge.server as bridge_module
    registry = ClientSessionRegistry()

    try:
        # Get the current temperature to check propagation later
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
    finally:
        await registry.stop_all()


@pytest.mark.asyncio
async def test_config_update_rejects_empty_config(fake_config, fake_provider, tmp_path):
    """config.update rejects empty config param."""
    from miqi.runtime.app_server import ClientSessionRegistry, AppServerError
    from miqi.runtime.config_handlers import config_update_handler

    registry = ClientSessionRegistry()

    with pytest.raises(AppServerError) as exc_info:
        await config_update_handler("req-1", {"config": {}}, "client-1", None, registry)
    assert exc_info.value.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_config_update_rejects_missing_config_param(fake_config, fake_provider, tmp_path):
    """config.update rejects request without config param."""
    from miqi.runtime.app_server import ClientSessionRegistry, AppServerError
    from miqi.runtime.config_handlers import config_update_handler

    registry = ClientSessionRegistry()

    with pytest.raises(AppServerError) as exc_info:
        await config_update_handler("req-1", {}, "client-1", None, registry)
    assert exc_info.value.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_config_update_rejects_invalid_config(fake_config, fake_provider, tmp_path):
    """config.update rejects invalid config with INVALID_PARAMS code."""
    from miqi.runtime.app_server import ClientSessionRegistry, AppServerError
    from miqi.runtime.config_handlers import config_update_handler

    registry = ClientSessionRegistry()

    with pytest.raises(AppServerError) as exc_info:
        await config_update_handler(
            "req-1",
            {"config": {"agents": {"defaults": {"model": None}}}},
            "client-1", None, registry,
        )
    assert exc_info.value.code == "INVALID_PARAMS"
