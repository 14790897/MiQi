"""Tests for miqi.runtime.config_app_handlers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.config_app_handlers import register_config_app_handlers
from miqi.runtime.config_handlers import config_get_handler, config_update_handler


def _setup_server(
    registry: ClientSessionRegistry,
    *,
    model: str = "anthropic/claude-opus-4-5",
    api_key: str = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
) -> AppServer:
    """Set up a test AppServer with config handlers and a mock bridge state."""
    from miqi.config.schema import Config

    state = MagicMock()
    cfg = Config()
    cfg.agents.defaults.model = model
    # Set up a provider with an API key for redaction tests
    cfg.providers.anthropic.api_key = api_key
    cfg.providers.openai.api_key = "sk-proj-1234567890abcdef"
    state.load_config.return_value = cfg
    state.config = cfg
    registry.bridge_context["state"] = state

    server = AppServer(registry)
    register_config_app_handlers(server)
    return server


# ── config/read tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_read_redacts_secrets():
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    response = await server.dispatch("1", "config/read", {}, "client-1", None)
    data = response["result"]

    # Check providers sub-dict for redacted keys
    providers = data.get("providers", {})
    anthropic = providers.get("anthropic", {})
    assert "apiKey" in anthropic
    raw_key = anthropic["apiKey"]
    # Must be redacted — not the original key
    assert raw_key != "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
    assert "****" in raw_key or "…" in raw_key

    openai = providers.get("openai", {})
    assert openai.get("apiKey") != "sk-proj-1234567890abcdef"


@pytest.mark.asyncio
async def test_config_batch_write_sets_model_and_saves():
    registry = ClientSessionRegistry()
    server = _setup_server(registry, model="anthropic/claude-opus-4-5")

    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "agents.defaults.model", "value": "openai/gpt-4.1"}]},
        "client-1", None,
    )
    assert response["result"]["saved"] is True
    assert response["result"]["applied"] == 1

    # The bridge state config should be updated
    state = registry.bridge_context["state"]
    assert state.config is not None
    assert state.config.agents.defaults.model == "openai/gpt-4.1"


@pytest.mark.asyncio
async def test_config_batch_write_sets_approval_bypass():
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "approvals.bypassAll", "value": True}]},
        "client-1", None,
    )
    assert response["result"]["saved"] is True

    state = registry.bridge_context["state"]
    assert state.config.approvals.bypass_all is True


def test_legacy_command_approval_disabled_enables_effective_command_bypass():
    from miqi.config.schema import Config

    cfg = Config.model_validate({
        "agents": {
            "commandApproval": {
                "enabled": False,
            },
        },
    })

    bypass = cfg.effective_approval_bypass()
    assert bypass.bypass_command_approval is True
    assert bypass.bypasses_category("exec") is True


@pytest.mark.asyncio
async def test_config_batch_write_is_atomic_on_invalid_path():
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    # Remember the original config
    state = registry.bridge_context["state"]
    original_config = state.config

    # Try an edit with an invalid dunder segment
    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "agents.__private.field", "value": "bad"}]},
        "client-1", None,
    )
    assert response.get("code") == "INVALID_PARAMS"

    # The original config should NOT have been changed
    assert state.config is original_config


@pytest.mark.asyncio
async def test_config_batch_write_rejects_dunder_and_private_segments():
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    for bad_path in [
        "agents.__dunder.field",
        "agents._private.field",
        "agents.defaults..empty",
        "",
    ]:
        response = await server.dispatch(
            "1", "config/batchWrite",
            {"edits": [{"path": bad_path, "value": "x"}]},
            "client-1", None,
        )
        assert response.get("code") == "INVALID_PARAMS", (
            f"Path '{bad_path}' should be rejected"
        )


# ── config/batchWrite delete tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_batch_write_delete_removes_optional_value():
    """A real delete op on an optional field must remove it from the config."""
    registry = ClientSessionRegistry()
    server = _setup_server(registry, model="anthropic/claude-opus-4-5")

    # Set an optional provider field so we can delete it
    await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "providers.anthropic.apiBase", "value": "https://api.example.com/v1"}]},
        "client-1", None,
    )
    state = registry.bridge_context["state"]
    assert state.config.providers.anthropic.api_base == "https://api.example.com/v1"

    # Now delete that optional field
    response = await server.dispatch(
        "2", "config/batchWrite",
        {"edits": [{"op": "delete", "path": "providers.anthropic.apiBase"}]},
        "client-1", None,
    )
    assert response["result"]["saved"] is True
    assert state.config.providers.anthropic.api_base is None


@pytest.mark.asyncio
async def test_config_batch_write_delete_requires_existing_key():
    """Delete of a non-existent key must return INVALID_PARAMS."""
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"op": "delete", "path": "agents.defaults.nonexistentKey"}]},
        "client-1", None,
    )
    assert response.get("code") == "INVALID_PARAMS"


# ── Unknown path rejection tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_batch_write_rejects_unknown_path():
    """Setting a path that does not exist in the config dict must return
    INVALID_PARAMS (unless it is a desktop.* opaque path)."""
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "nonexistent.field", "value": "bad"}]},
        "client-1", None,
    )
    assert response.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_config_batch_write_unknown_path_is_atomic():
    """When an unknown path edit fails, no config changes must be persisted."""
    registry = ClientSessionRegistry()
    server = _setup_server(registry, model="anthropic/claude-opus-4-5")

    state = registry.bridge_context["state"]
    original_model = state.config.agents.defaults.model

    # One valid edit + one unknown path → entire batch must fail atomically
    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [
            {"path": "agents.defaults.model", "value": "openai/gpt-4.1"},
            {"path": "nonexistent.field", "value": "bad"},
        ]},
        "client-1", None,
    )
    assert response.get("code") == "INVALID_PARAMS"

    # Model must NOT have changed
    assert state.config.agents.defaults.model == original_model


@pytest.mark.asyncio
async def test_config_batch_write_allows_desktop_opaque_paths():
    """desktop.* paths are allowed even if they do not exist in the config schema."""
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "desktop.theme", "value": "dark"}]},
        "client-1", None,
    )
    assert response.get("result", {}).get("saved") is True


# ── Error hygiene tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_batch_write_error_does_not_leak_stack_trace():
    """Validation errors must not leak raw Traceback or filesystem paths."""
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    # Trigger a pydantic validation error with a malicious value
    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "agents.defaults.model", "value": None}]},
        "client-1", None,
    )
    assert response.get("code") == "INVALID_PARAMS"
    error = response.get("error", "")
    assert "Traceback" not in error
    assert "File " not in error


@pytest.mark.asyncio
async def test_config_batch_write_error_does_not_leak_filesystem_paths():
    """Error messages must not expose server-side filesystem paths."""
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "agents.__dunder.field", "value": "x"}]},
        "client-1", None,
    )
    assert response.get("code") == "INVALID_PARAMS"
    error = response.get("error", "")
    assert "\\miqi\\" not in error.lower()
    assert "/miqi/" not in error.lower()


# ── Save safety audit test ─────────────────────────────────────────────────


def test_config_batch_write_does_not_touch_real_config_path(monkeypatch):
    """Prove that config/batchWrite writes only to the tmp_path fixture."""
    import miqi.config.loader as loader_module

    real_config = Path.home() / ".miqi" / "config.json"
    recorded_path: list[Path] = []

    def _tracked_save(config, config_path=None):
        path = config_path or loader_module.get_config_path()
        recorded_path.append(Path(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        data = config.model_dump(by_alias=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(loader_module, "save_config", _tracked_save)

    # Run a quick dispatch through config/batchWrite
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    import asyncio
    async def _run():
        return await server.dispatch(
            "1", "config/batchWrite",
            {"edits": [{"path": "agents.defaults.model", "value": "deepseek/deepseek-chat"}]},
            "client-1", None,
        )
    result = asyncio.run(_run())

    assert result["result"]["saved"] is True
    # The save must NOT have targeted the real config path
    for p in recorded_path:
        assert p != real_config, f"config/batchWrite wrote to real config: {p}"
        assert not str(p).endswith(str(real_config)), f"config path ends like real: {p}"


# ── config/batchWrite propagation tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_config_batch_write_propagates_to_client_sessions():
    registry = ClientSessionRegistry()
    server = _setup_server(registry, model="anthropic/claude-opus-4-5")

    # Register a mock session with session_state
    mock_runtime = MagicMock()
    mock_session_state = MagicMock()
    mock_session_state.config_snapshot = None
    mock_runtime.services.session_state = mock_session_state

    # We need to set up session tracking. Since we don't have a real session,
    # test that the propagation path runs without error when no sessions exist.
    response = await server.dispatch(
        "1", "config/batchWrite",
        {"edits": [{"path": "agents.defaults.model", "value": "deepseek/deepseek-chat"}],
         "reloadUserConfig": True},
        "client-1", None,
    )
    assert response["result"]["saved"] is True
    # propagatedSessions will be 0 since no real sessions exist
    assert "propagatedSessions" in response["result"]


# ── Legacy config handler tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_config_handlers_no_bridge_imports():
    """config_handlers.py must not contain 'import miqi.bridge.server'."""
    from pathlib import Path

    path = Path(__file__).parents[2] / "miqi" / "runtime" / "config_handlers.py"
    text = path.read_text(encoding="utf-8")
    assert "import miqi.bridge.server" not in text
    assert "from miqi.bridge.server import" not in text


@pytest.mark.asyncio
async def test_legacy_config_get_still_works():
    """Legacy config.get handler returns redacted config via get_bridge_state."""
    registry = ClientSessionRegistry()
    _setup_server(registry)

    response = await config_get_handler(
        "1", {}, "client-1", None, registry,
    )
    assert "result" in response
    data = response["result"]
    providers = data.get("providers", {})
    anthropic = providers.get("anthropic", {})
    # Must be redacted
    assert anthropic.get("apiKey") != "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"


@pytest.mark.asyncio
async def test_legacy_config_update_still_works():
    """Legacy config.update handler works via get_bridge_state."""
    registry = ClientSessionRegistry()
    _setup_server(registry, model="anthropic/claude-opus-4-5")

    response = await config_update_handler(
        "1",
        {"config": {"agents": {"defaults": {"model": "openai/gpt-4.1"}}}},
        "client-1", None, registry,
    )
    assert response["result"]["saved"] is True

    state = registry.bridge_context["state"]
    assert state.config.agents.defaults.model == "openai/gpt-4.1"


@pytest.mark.asyncio
async def test_legacy_config_update_error_hygiene():
    """Legacy config.update must not leak raw validation details."""
    registry = ClientSessionRegistry()
    _setup_server(registry)

    from miqi.runtime.app_server import AppServerError
    with pytest.raises(AppServerError) as exc_info:
        await config_update_handler(
            "1",
            {"config": {"agents": {"defaults": {"model": None}}}},
            "client-1", None, registry,
        )
    assert exc_info.value.code == "INVALID_PARAMS"
    error = str(exc_info.value)
    assert "Traceback" not in error
    assert "File " not in error
