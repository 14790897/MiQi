"""Tests for miqi.runtime.model_app_handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.model_app_handlers import register_model_app_handlers


def _setup_server(registry: ClientSessionRegistry, model: str = "anthropic/claude-opus-4-5") -> AppServer:
    """Set up a test AppServer with model handlers registered and bridge_state."""
    state = MagicMock()
    cfg = MagicMock()
    cfg.agents.defaults.model = model
    cfg.get_provider_name.return_value = model.split("/", 1)[0]
    state.load_config.return_value = cfg
    registry.bridge_context["state"] = state

    server = AppServer(registry)
    register_model_app_handlers(server)
    return server


@pytest.mark.asyncio
async def test_model_list_returns_codex_style_models():
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    response = await server.dispatch("1", "model/list", {}, "client-1", None)
    assert "models" in response["result"]
    models = response["result"]["models"]
    assert len(models) > 0

    first = models[0]
    assert "id" in first
    assert "provider" in first
    assert "providerDisplayName" in first
    assert "default" in first
    # Current model should be marked default
    current = next(m for m in models if m["id"] == "anthropic/claude-opus-4-5")
    assert current["default"] is True


@pytest.mark.asyncio
async def test_model_list_include_hidden_controls_hidden_rows():
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    visible = await server.dispatch("1", "model/list", {"includeHidden": False}, "client-1", None)
    all_models = await server.dispatch("2", "model/list", {"includeHidden": True}, "client-1", None)

    visible_ids = {m["id"] for m in visible["result"]["models"]}
    all_ids = {m["id"] for m in all_models["result"]["models"]}
    assert visible_ids <= all_ids
    assert len(all_ids) >= len(visible_ids)


@pytest.mark.asyncio
async def test_model_provider_capabilities_default_provider():
    registry = ClientSessionRegistry()
    server = _setup_server(registry, model="openai/gpt-4.1")

    response = await server.dispatch(
        "1", "modelProvider/capabilities/read", {}, "client-1", None,
    )
    caps = response["result"]["capabilities"]
    assert caps["provider"] == "openai"
    assert caps["providerType"] == "openai"
    assert "supportsStreaming" in caps
    assert "supportsTools" in caps
    # No api_key exposed
    for key in caps:
        assert "key" not in key.lower()


@pytest.mark.asyncio
async def test_model_provider_capabilities_explicit_provider():
    registry = ClientSessionRegistry()
    server = _setup_server(registry, model="anthropic/claude-opus-4-5")

    response = await server.dispatch(
        "1", "modelProvider/capabilities/read",
        {"provider": "deepseek"}, "client-1", None,
    )
    caps = response["result"]["capabilities"]
    assert caps["provider"] == "deepseek"
    assert caps["providerType"] == "openai"  # DeepSeek is OpenAI-compatible


@pytest.mark.asyncio
async def test_model_provider_capabilities_unknown_provider_rejected():
    registry = ClientSessionRegistry()
    server = _setup_server(registry)

    response = await server.dispatch(
        "1", "modelProvider/capabilities/read",
        {"provider": "nonexistent-provider-xyz"}, "client-1", None,
    )
    assert response.get("code") == "NOT_FOUND"
