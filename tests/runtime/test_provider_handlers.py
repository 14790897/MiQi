"""Tests for provider handlers — Phase 35.2 / hardening.

Validates providers.list, providers.test, and providers.update
migrated from bridge legacy to AppServer async handlers.
"""

import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _make_config_with_workspace():
    """Create a Config with a temp workspace path for handler tests."""
    from miqi.config.schema import Config
    config = Config()
    config.agents.defaults.workspace = tempfile.mkdtemp()
    return config


def _provider_entry(result: dict, name: str) -> dict:
    return next(p for p in result["result"]["providers"] if p["name"] == name)


# ── providers.list ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_providers_list_returns_providers(registry_with_state):
    """providers.list should return a list of provider entries with expected shape."""
    from miqi.runtime.provider_handlers import providers_list_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    mock_state.load_config.return_value = config

    result = await providers_list_handler("req-1", {}, "client-1", None, registry)

    providers = result["result"]["providers"]
    assert result["result"]["active_model"] == config.agents.defaults.model
    assert "active_provider" in result["result"]
    assert isinstance(providers, list)
    assert len(providers) > 0, "Expected at least one provider"

    # Verify shape of each entry
    for p in providers:
        assert "name" in p
        assert "display_name" in p
        assert "env_key" in p
        assert "provider_type" in p
        assert "configured" in p
        assert "api_key_hint" in p
        assert "verification_status" in p


@pytest.mark.asyncio
async def test_providers_list_api_key_hint_redacted(registry_with_state):
    """Providers list must not leak full API keys."""
    from miqi.runtime.provider_handlers import providers_list_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    mock_state.load_config.return_value = config

    result = await providers_list_handler("req-1", {}, "client-1", None, registry)

    for p in result["result"]["providers"]:
        hint = p.get("api_key_hint") or ""
        # If there is a hint, it should be redacted (no long raw key)
        if hint and hint not in ("***", "None", None):
            assert "…" in hint or len(hint) < 16, (
                f"api_key_hint for {p['name']} looks like a full key: {hint}"
            )


@pytest.mark.asyncio
async def test_providers_list_reports_verification_status(registry_with_state):
    """providers.list distinguishes missing, unverified, success, and stale records."""
    from miqi.runtime.provider_handlers import (
        _provider_fingerprint,
        providers_list_handler,
    )

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-test-deepseek"
    config.providers.openai.api_key = "sk-test-openai"
    fingerprint = _provider_fingerprint(config.providers.deepseek)
    config.desktop["providerVerification"] = {
        "deepseek": {
            "status": "success",
            "fingerprint": fingerprint,
            "checkedAt": "2026-07-09T00:00:00+00:00",
            "message": "ok",
        },
        "openai": {
            "status": "success",
            "fingerprint": "stale",
            "checkedAt": "2026-07-09T00:00:00+00:00",
            "message": "stale",
        },
    }
    mock_state.load_config.return_value = config

    result = await providers_list_handler("req-1", {}, "client-1", None, registry)

    assert _provider_entry(result, "deepseek")["verification_status"] == "success"
    assert _provider_entry(result, "openai")["verification_status"] == "unverified"
    assert _provider_entry(result, "anthropic")["verification_status"] == "missing"


# ── providers.test ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_providers_test_missing_provider_name():
    """providers.test should reject empty provider_name."""
    from miqi.runtime.provider_handlers import providers_test_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="provider_name is required"):
        await providers_test_handler("req-1", {}, "client-1", None, registry)


@pytest.mark.asyncio
async def test_providers_test_unknown_provider():
    """providers.test should reject unknown provider names."""
    from miqi.runtime.provider_handlers import providers_test_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="Unknown provider"):
        await providers_test_handler(
            "req-1",
            {"provider_name": "nonexistent-xyz-123", "api_key": "sk-test-key"},
            "client-1", None, registry,
        )


@pytest.mark.asyncio
async def test_providers_test_no_api_key(registry_with_state):
    """providers.test should reject missing API key (when not in config)."""
    from miqi.runtime.provider_handlers import providers_test_handler
    from miqi.runtime.app_server import AppServerError

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    mock_state.load_config.return_value = config

    with pytest.raises(AppServerError, match="No API key configured"):
        await providers_test_handler(
            "req-1",
            {"provider_name": "anthropic"},
            "client-1", None, registry,
        )


@pytest.mark.asyncio
async def test_providers_test_persists_success_for_saved_config(registry_with_state, monkeypatch):
    """providers.test records success when testing the saved provider config."""
    from miqi.providers.openai_provider import OpenAIProvider
    from miqi.runtime.provider_handlers import providers_test_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-test-deepseek"
    mock_state.load_config.return_value = config
    saved = []

    async def fake_chat(self, *args, **kwargs):
        return SimpleNamespace(content="ok")

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: saved.append(cfg))

    result = await providers_test_handler(
        "req-1",
        {"provider_name": "deepseek"},
        "client-1", None, registry,
    )

    assert result["result"]["ok"] is True
    assert saved
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "success"


@pytest.mark.asyncio
async def test_providers_test_uses_requested_model(registry_with_state, monkeypatch):
    """providers.test must test the requested provider model, not OpenAI's default."""
    from miqi.providers.openai_provider import OpenAIProvider
    from miqi.runtime.provider_handlers import providers_test_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-test-deepseek"
    mock_state.load_config.return_value = config
    seen_models = []

    async def fake_chat(self, *args, **kwargs):
        seen_models.append(kwargs.get("model"))
        return SimpleNamespace(content="ok")

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: None)

    result = await providers_test_handler(
        "req-1",
        {"provider_name": "deepseek", "model": "deepseek-v4-flash"},
        "client-1", None, registry,
    )

    assert result["result"]["ok"] is True
    assert result["result"]["model"] == "deepseek-v4-flash"
    assert seen_models == ["deepseek-v4-flash"]


@pytest.mark.asyncio
async def test_providers_test_accepts_empty_success_response(registry_with_state, monkeypatch):
    """A connection test validates credentials/model acceptance, not answer text quality."""
    from miqi.providers.base import LLMResponse
    from miqi.providers.openai_provider import OpenAIProvider
    from miqi.runtime.provider_handlers import providers_test_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-test-deepseek"
    mock_state.load_config.return_value = config

    async def fake_chat(self, *args, **kwargs):
        return LLMResponse(content="", finish_reason="stop")

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: None)

    result = await providers_test_handler(
        "req-1",
        {"provider_name": "deepseek", "model": "deepseek-v4-flash"},
        "client-1", None, registry,
    )

    assert result["result"]["ok"] is True


@pytest.mark.asyncio
async def test_providers_test_does_not_persist_unsaved_api_base(registry_with_state, monkeypatch):
    """Testing temporary edit-sheet values must not mark the saved config verified."""
    from miqi.providers.openai_provider import OpenAIProvider
    from miqi.runtime.provider_handlers import providers_test_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.custom.api_key = "sk-test-custom"
    config.providers.custom.api_base = "https://saved.example/v1"
    mock_state.load_config.return_value = config
    saved = []

    async def fake_chat(self, *args, **kwargs):
        return SimpleNamespace(content="ok")

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: saved.append(cfg))

    result = await providers_test_handler(
        "req-1",
        {"provider_name": "custom", "api_base": "https://unsaved.example/v1"},
        "client-1", None, registry,
    )

    assert result["result"]["ok"] is True
    assert saved == []
    assert "providerVerification" not in config.desktop


@pytest.mark.asyncio
async def test_providers_test_persists_failure_for_saved_config(registry_with_state, monkeypatch):
    """providers.test records failure when the saved provider config cannot connect."""
    from miqi.providers.openai_provider import OpenAIProvider
    from miqi.runtime.app_server import AppServerError
    from miqi.runtime.provider_handlers import providers_test_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-test-deepseek"
    mock_state.load_config.return_value = config
    saved = []

    async def fake_chat(self, *args, **kwargs):
        raise RuntimeError("bad key")

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: saved.append(cfg))

    with pytest.raises(AppServerError, match="Provider test failed"):
        await providers_test_handler(
            "req-1",
            {"provider_name": "deepseek"},
            "client-1", None, registry,
        )

    assert saved
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "failed"


@pytest.mark.asyncio
async def test_providers_test_treats_error_response_as_failure(registry_with_state, monkeypatch):
    """Provider adapters may return LLMResponse(finish_reason='error') instead of raising."""
    from miqi.providers.base import LLMResponse
    from miqi.providers.openai_provider import OpenAIProvider
    from miqi.runtime.app_server import AppServerError
    from miqi.runtime.provider_handlers import providers_test_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "bad-key"
    mock_state.load_config.return_value = config
    saved = []

    async def fake_chat(self, *args, **kwargs):
        return LLMResponse(
            content="Error calling LLM: invalid api key",
            finish_reason="error",
            error_kind="auth",
        )

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: saved.append(cfg))

    with pytest.raises(AppServerError, match="Provider test failed"):
        await providers_test_handler(
            "req-1",
            {"provider_name": "deepseek"},
            "client-1", None, registry,
        )

    assert saved
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "failed"


# ── providers.update ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_providers_update_missing_provider_name():
    """providers.update should reject empty provider_name."""
    from miqi.runtime.provider_handlers import providers_update_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="provider_name is required"):
        await providers_update_handler("req-1", {}, "client-1", None, registry)


@pytest.mark.asyncio
async def test_providers_update_unknown_provider():
    """providers.update should reject unknown provider names."""
    from miqi.runtime.provider_handlers import providers_update_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="Unknown provider"):
        await providers_update_handler(
            "req-1",
            {"provider_name": "nonexistent-xyz-123"},
            "client-1", None, registry,
        )


@pytest.mark.asyncio
async def test_providers_update_no_fields(registry_with_state):
    """providers.update should reject request with no update fields."""
    from miqi.runtime.provider_handlers import providers_update_handler
    from miqi.runtime.app_server import AppServerError

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    mock_state.load_config.return_value = config

    with pytest.raises(AppServerError, match="No fields to update"):
        await providers_update_handler(
            "req-1",
            {"provider_name": "openai"},
            "client-1", None, registry,
        )


@pytest.mark.asyncio
async def test_providers_update_marks_changed_config_unverified(registry_with_state, monkeypatch):
    """Saving provider credentials invalidates the previous verification status."""
    from miqi.runtime.provider_handlers import providers_update_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-old"
    config.desktop["providerVerification"] = {
        "deepseek": {
            "status": "success",
            "fingerprint": "old",
            "checkedAt": "2026-07-09T00:00:00+00:00",
            "message": "ok",
        },
    }
    mock_state.load_config.return_value = config
    saved = []
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: saved.append(cfg))

    result = await providers_update_handler(
        "req-1",
        {"provider_name": "deepseek", "api_key": "sk-new"},
        "client-1", None, registry,
    )

    assert result["result"]["saved"] is True
    assert saved
    assert config.providers.deepseek.api_key == "sk-new"
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "unverified"
