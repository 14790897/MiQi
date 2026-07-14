"""Tests for provider handlers — Phase 35.2 / hardening.

Validates providers.list, providers.test, and providers.update
migrated from bridge legacy to AppServer async handlers.
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_FIXTURE_BUNDLE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "builtin_models"
_FIXTURE_BUILTIN_KEY = "sk-test-deepseek-internal-placeholder-not-a-real-key"


def _internal_unlock_code() -> str:
    return "".join(["wei", "guan", "ji", "yuan"])


@pytest.fixture(autouse=True)
def _reset_builtin_credentials():
    from miqi.providers import builtin_credentials as bc

    bc._bundle_dir_override = _FIXTURE_BUNDLE_DIR
    bc.BUILTIN_KEY_PROVIDER.deactivate()
    yield
    bc.BUILTIN_KEY_PROVIDER.deactivate()
    bc._bundle_dir_override = None


def _make_config_with_workspace():
    """Create a Config with a temp workspace path for handler tests."""
    from miqi.config.schema import Config
    config = Config()
    config.agents.defaults.workspace = tempfile.mkdtemp()
    return config


def _provider_entry(result: dict, name: str) -> dict:
    return next(p for p in result["result"]["providers"] if p["name"] == name)


def _unlock_builtin_fixture():
    from miqi.providers.builtin_credentials import BUILTIN_KEY_PROVIDER

    metadata = BUILTIN_KEY_PROVIDER.unlock(_internal_unlock_code())
    assert metadata is not None
    return BUILTIN_KEY_PROVIDER


def test_builtin_bundle_dir_env_override(monkeypatch):
    from miqi.providers import builtin_credentials as bc

    bc._bundle_dir_override = None
    monkeypatch.setenv("MIQI_BUILTIN_MODELS_DIR", str(_FIXTURE_BUNDLE_DIR))
    bc.BUILTIN_KEY_PROVIDER.deactivate()

    metadata = bc.BUILTIN_KEY_PROVIDER.unlock(_internal_unlock_code())

    assert metadata is not None
    assert metadata["providers"][0]["provider"] == "deepseek"


def _trial_config(model: str = "deepseek-v4-flash"):
    config = _make_config_with_workspace()
    config.agents.defaults.model = model
    config.desktop["builtinModel"] = {
        "enabled": True,
        "bundleId": "internal_deepseek",
        "licenseId": "internal_deepseek",
        "providers": [
            {
                "provider": "deepseek",
                "models": ["deepseek-v4-flash"],
                "defaultModel": "deepseek-v4-flash",
            },
        ],
    }
    config.desktop["providerCredentials"] = {"active": {"deepseek": "builtin"}}
    return config


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
    config.agents.defaults.model = "deepseek-v4-flash"
    fingerprint = _provider_fingerprint(config.providers.deepseek, "deepseek-v4-flash")
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
    assert result["result"]["model"] == "deepseek-v4-flash"


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
async def test_providers_test_persists_with_default_api_base_for_saved_config(
    registry_with_state, monkeypatch
):
    """Passing a provider's default API base from the UI still tests the saved config."""
    from miqi.providers.openai_provider import OpenAIProvider
    from miqi.runtime.provider_handlers import providers_test_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-test-deepseek"
    config.providers.deepseek.api_base = None
    mock_state.load_config.return_value = config
    saved = []

    async def fake_chat(self, *args, **kwargs):
        return SimpleNamespace(content="ok")

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: saved.append(cfg))

    result = await providers_test_handler(
        "req-1",
        {
            "provider_name": "deepseek",
            "api_base": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-flash",
        },
        "client-1", None, registry,
    )

    assert result["result"]["ok"] is True
    assert saved
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "success"


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
async def test_providers_test_uses_builtin_key_for_unlocked_trial(registry_with_state, monkeypatch):
    """Unlocked built-in credentials should support the saved-config test path."""
    from miqi.providers.openai_provider import OpenAIProvider
    from miqi.runtime.provider_handlers import providers_test_handler

    _unlock_builtin_fixture()
    registry, mock_state = registry_with_state
    config = _trial_config()
    config.providers.deepseek.api_key = "sk-user-wrong"
    mock_state.load_config.return_value = config
    seen_api_keys = []

    async def fake_chat(self, *args, **kwargs):
        seen_api_keys.append(self.api_key)
        return SimpleNamespace(content="ok")

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: None)

    result = await providers_test_handler(
        "req-1",
        {"provider_name": "deepseek", "model": "deepseek-v4-flash"},
        "client-1", None, registry,
    )

    assert result["result"]["ok"] is True
    assert seen_api_keys == [_FIXTURE_BUILTIN_KEY]
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "success"


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
    assert config.desktop["providerCredentials"]["active"]["deepseek"] == "user"
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "unverified"


@pytest.mark.asyncio
async def test_providers_update_marks_api_base_and_headers_unverified(
    registry_with_state, monkeypatch
):
    """Changing API base or headers invalidates the previous verification status."""
    from miqi.runtime.provider_handlers import providers_update_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-old"
    config.providers.deepseek.api_base = "https://old.example/v1"
    config.desktop["providerVerification"] = {
        "deepseek": {
            "status": "success",
            "fingerprint": "old",
            "checkedAt": "2026-07-09T00:00:00+00:00",
            "message": "ok",
        },
    }
    mock_state.load_config.return_value = config
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: None)

    await providers_update_handler(
        "req-1",
        {"provider_name": "deepseek", "api_base": "https://new.example/v1"},
        "client-1", None, registry,
    )
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "unverified"

    config.desktop["providerVerification"]["deepseek"]["status"] = "success"
    await providers_update_handler(
        "req-2",
        {"provider_name": "deepseek", "extra_headers": {"X-Test": "1"}},
        "client-1", None, registry,
    )
    assert config.desktop["providerVerification"]["deepseek"]["status"] == "unverified"


@pytest.mark.asyncio
async def test_providers_update_fills_default_api_base_for_key_only_config(
    registry_with_state, monkeypatch
):
    """Saving only an API key should still produce a runnable provider config."""
    from miqi.runtime.provider_handlers import providers_update_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = ""
    config.providers.deepseek.api_base = None
    mock_state.load_config.return_value = config
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: None)

    result = await providers_update_handler(
        "req-1",
        {"provider_name": "deepseek", "api_key": "sk-new"},
        "client-1", None, registry,
    )

    assert result["result"]["saved"] is True
    assert config.providers.deepseek.api_key == "sk-new"
    assert config.providers.deepseek.api_base == "https://api.deepseek.com/v1"


# Built-in model unlock (issue #191)


def test_builtin_fallback_used_when_no_user_key():
    _unlock_builtin_fixture()
    config = _trial_config()

    assert config.get_provider_name() == "deepseek"
    assert config.get_api_key() == _FIXTURE_BUILTIN_KEY


def test_active_builtin_overrides_user_key():
    _unlock_builtin_fixture()
    config = _trial_config()
    config.providers.deepseek.api_key = "sk-user-key"

    assert config.get_api_key() == _FIXTURE_BUILTIN_KEY


def test_active_user_credential_uses_user_key():
    _unlock_builtin_fixture()
    config = _trial_config()
    config.providers.deepseek.api_key = "sk-user-key"
    config.desktop["providerCredentials"]["active"]["deepseek"] = "user"

    assert config.get_api_key() == "sk-user-key"


def test_builtin_does_not_leak_to_other_providers():
    _unlock_builtin_fixture()
    config = _trial_config(model="anthropic/claude-opus-4-5")

    assert config.get_provider_name() is None
    assert config.get_api_key() is None


def test_builtin_bundle_only_unlocks_deepseek():
    _unlock_builtin_fixture()
    config = _trial_config(model="gemini/gemini-2.5-flash")

    assert config.get_provider_name() is None
    assert config.get_api_key() is None


def test_builtin_disabled_is_unreachable():
    _unlock_builtin_fixture()
    config = _trial_config()
    config.desktop["builtinModel"]["enabled"] = False

    assert config.get_provider_name() is None
    assert config.get_api_key() is None


def test_builtin_key_never_persisted_to_disk(tmp_path):
    import json

    from miqi.config.loader import load_config, save_config

    _unlock_builtin_fixture()
    config = _trial_config()
    config_path = tmp_path / "config.json"

    save_config(config, config_path)
    raw = config_path.read_text(encoding="utf-8")
    assert _FIXTURE_BUILTIN_KEY not in raw
    data = json.loads(raw)
    assert data["desktop"]["builtinModel"]["enabled"] is True
    assert "api_key" not in data["desktop"]["builtinModel"]
    assert "key" not in data["desktop"]["builtinModel"]

    loaded = load_config(config_path)
    assert loaded.desktop["builtinModel"]["providers"][0]["provider"] == "deepseek"


def test_make_provider_uses_builtin_for_trial_user():
    from miqi.providers.factory import make_provider

    _unlock_builtin_fixture()
    config = _trial_config()
    provider = make_provider(config)

    assert provider.api_key == _FIXTURE_BUILTIN_KEY


def test_make_provider_builtin_active_wins_over_user_key():
    from miqi.providers.factory import make_provider

    _unlock_builtin_fixture()
    config = _trial_config()
    config.providers.deepseek.api_key = "sk-user-key"
    provider = make_provider(config)

    assert provider.api_key == _FIXTURE_BUILTIN_KEY


def test_make_provider_user_active_wins():
    from miqi.providers.factory import make_provider

    _unlock_builtin_fixture()
    config = _trial_config()
    config.providers.deepseek.api_key = "sk-user-key"
    config.desktop["providerCredentials"]["active"]["deepseek"] = "user"
    provider = make_provider(config)

    assert provider.api_key == "sk-user-key"


@pytest.mark.asyncio
async def test_providers_list_reports_builtin_as_unlocked(registry_with_state):
    from miqi.runtime.provider_handlers import providers_list_handler

    _unlock_builtin_fixture()
    registry, mock_state = registry_with_state
    config = _trial_config()
    mock_state.load_config.return_value = config

    result = await providers_list_handler("req-1", {}, "client-1", None, registry)

    deepseek = _provider_entry(result, "deepseek")
    assert deepseek["configured"] is False
    assert deepseek["builtin_unlocked"] is True
    assert deepseek["credential_source"] == "builtin"
    assert deepseek["active_credential"] == "builtin"
    assert deepseek["verification_status"] == "unverified"
    assert deepseek["api_key_hint"] is None


@pytest.mark.asyncio
async def test_builtin_unlock_handler_valid_code(registry_with_state, monkeypatch):
    from miqi.runtime.provider_handlers import builtin_model_unlock_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.agents.defaults.model = "anthropic/claude-opus-4-5"
    mock_state.load_config.return_value = config
    saved = []
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: saved.append(cfg))

    result = await builtin_model_unlock_handler(
        "req-1", {"activation_code": _internal_unlock_code()}, "client-1", None, registry
    )

    assert result["result"]["providers"][0]["provider"] == "deepseek"
    assert len(result["result"]["providers"]) == 1
    assert result["result"]["userKeyPresent"] is False
    assert result["result"]["activatedModel"] is True
    assert config.agents.defaults.model == "deepseek-v4-flash"
    assert saved
    state = config.desktop["builtinModel"]
    assert state["enabled"] is True
    assert state["providers"][0]["provider"] == "deepseek"
    assert len(state["providers"]) == 1
    assert "api_key" not in state and "key" not in state and "token" not in state
    assert "sealedCredential" in state
    assert _FIXTURE_BUILTIN_KEY not in str(state["sealedCredential"])
    assert config.desktop["providerCredentials"]["active"]["deepseek"] == "builtin"


@pytest.mark.asyncio
async def test_builtin_unlock_handler_overrides_existing_user_deepseek(registry_with_state, monkeypatch):
    from miqi.runtime.provider_handlers import builtin_model_unlock_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-deepseek-user"
    config.agents.defaults.model = "openai/gpt-4o"
    mock_state.load_config.return_value = config
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: None)

    result = await builtin_model_unlock_handler(
        "req-1", {"activation_code": _internal_unlock_code()}, "client-1", None, registry
    )

    assert result["result"]["userKeyPresent"] is True
    assert result["result"]["activatedModel"] is True
    assert config.agents.defaults.model == "deepseek-v4-flash"
    assert config.desktop["providerCredentials"]["active"]["deepseek"] == "builtin"
    assert config.get_api_key() == _FIXTURE_BUILTIN_KEY


@pytest.mark.asyncio
async def test_builtin_unlock_survives_bridge_restart(registry_with_state, monkeypatch):
    from miqi.providers.builtin_credentials import BUILTIN_KEY_PROVIDER
    from miqi.runtime.provider_handlers import builtin_model_unlock_handler

    registry, mock_state = registry_with_state
    config = _make_config_with_workspace()
    config.providers.deepseek.api_key = "sk-user-wrong"
    mock_state.load_config.return_value = config
    monkeypatch.setattr("miqi.config.loader.save_config", lambda cfg: None)

    await builtin_model_unlock_handler(
        "req-1", {"activation_code": _internal_unlock_code()}, "client-1", None, registry
    )
    BUILTIN_KEY_PROVIDER.deactivate()

    assert config.get_api_key("deepseek/deepseek-v4-flash") == _FIXTURE_BUILTIN_KEY


@pytest.mark.asyncio
async def test_builtin_unlock_handler_invalid_code(registry_with_state):
    from miqi.runtime.app_server import AppServerError
    from miqi.runtime.provider_handlers import builtin_model_unlock_handler

    registry, mock_state = registry_with_state
    mock_state.load_config.return_value = _make_config_with_workspace()

    with pytest.raises(AppServerError) as exc_info:
        await builtin_model_unlock_handler(
            "req-1", {"activation_code": "wrong-code"}, "client-1", None, registry
        )

    assert exc_info.value.code == "INVALID_CODE"
