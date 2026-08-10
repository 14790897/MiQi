"""Provider handler regression tests — #602 deepseek model mismatch.

Reproduces the bug where saving a DeepSeek API key left the global default
model at "anthropic/claude-opus-4-5", so the DeepSeek API was called with a
Claude model name and rejected with 400 invalid_request_error. Also covers
providers.list mislabeling the global model as DeepSeek's configured model.
"""

from __future__ import annotations

import pytest

from miqi.runtime.app_server import ClientSessionRegistry
from miqi.runtime.provider_handlers import (
    providers_list_handler,
    providers_update_handler,
)


def _make_registry(model: str, **provider_keys) -> ClientSessionRegistry:
    """Registry with a real Config whose default model is `model`.

    provider_keys: provider_name -> api_key to configure.
    """
    from unittest.mock import MagicMock

    from miqi.config.schema import Config

    cfg = Config()
    cfg.agents.defaults.model = model
    for name, key in provider_keys.items():
        setattr(getattr(cfg.providers, name), "api_key", key)

    state = MagicMock()
    state.load_config.return_value = cfg
    state.config = cfg

    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state
    return registry


@pytest.mark.asyncio
async def test_providers_list_does_not_mislabel_global_model_as_deepseek_model():
    """providers.list must not report the claude default as deepseek's configured_model."""
    registry = _make_registry("anthropic/claude-opus-4-5", deepseek="sk-ds-1234567890")

    result = await providers_list_handler("r1", {}, "client-1", None, registry)
    providers = {p["name"]: p for p in result["result"]["providers"]}

    deepseek = providers["deepseek"]
    assert deepseek["configured"] is True
    # The default model belongs to anthropic — deepseek must NOT claim it.
    assert deepseek["configured_model"] is None
    assert result["result"]["active_model"] == "anthropic/claude-opus-4-5"
    assert result["result"]["active_provider"] == "anthropic"


@pytest.mark.asyncio
async def test_providers_list_reports_model_when_it_belongs_to_provider():
    """When the default model genuinely matches the provider, configured_model is set."""
    registry = _make_registry("deepseek-v4-flash", deepseek="sk-ds-1234567890")

    result = await providers_list_handler("r1", {}, "client-1", None, registry)
    providers = {p["name"]: p for p in result["result"]["providers"]}

    deepseek = providers["deepseek"]
    assert deepseek["configured_model"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_providers_update_switches_default_model_to_saved_provider():
    """Saving a DeepSeek key while the default model is unusable (no key) must
    switch the default model to DeepSeek's — otherwise chat calls the DeepSeek
    API with a Claude model name (#602)."""
    from unittest import mock

    registry = _make_registry("anthropic/claude-opus-4-5", deepseek="sk-ds-1234567890")
    state = registry.bridge_context["state"]

    # save_config is imported inside the handler from miqi.config.loader
    with mock.patch("miqi.config.loader.save_config"):
        result = await providers_update_handler(
            "r1",
            {"provider_name": "deepseek", "api_key": "sk-ds-9876543210"},
            "client-1", None, registry,
        )

    assert result["result"]["saved"] is True
    # Default model must now be a DeepSeek model, not the claude default.
    assert state.config.agents.defaults.model == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_providers_update_keeps_model_when_provider_still_configured():
    """If the current default provider still has a key, saving another provider's
    key must NOT change the default model."""
    registry = _make_registry(
        "anthropic/claude-opus-4-5",
        anthropic="sk-ant-api03-1234567890abcdef",
        deepseek="sk-ds-1234567890",
    )
    state = registry.bridge_context["state"]

    from unittest import mock

    with mock.patch("miqi.config.loader.save_config"):
        await providers_update_handler(
            "r1",
            {"provider_name": "deepseek", "api_key": "sk-ds-9876543210"},
            "client-1", None, registry,
        )

    # anthropic still configured — default model must stay untouched.
    assert state.config.agents.defaults.model == "anthropic/claude-opus-4-5"


@pytest.mark.asyncio
async def test_providers_update_explicit_model_override_wins():
    """An explicit model param overrides the auto-switch behavior."""
    registry = _make_registry("anthropic/claude-opus-4-5")
    state = registry.bridge_context["state"]

    from unittest import mock

    with mock.patch("miqi.config.loader.save_config"):
        await providers_update_handler(
            "r1",
            {"provider_name": "deepseek", "api_key": "sk-ds-9876543210", "model": "deepseek-v4-pro"},
            "client-1", None, registry,
        )

    assert state.config.agents.defaults.model == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_providers_update_api_base_also_triggers_auto_switch():
    """Saving a local provider's api_base (no key) must also trigger the
    auto-switch when the current default model's provider is unusable."""
    from unittest.mock import MagicMock

    from miqi.config.schema import Config

    cfg = Config()
    cfg.agents.defaults.model = "anthropic/claude-opus-4-5"
    # vllm is a local provider — configured via api_base only
    cfg.providers.vllm.api_base = "http://localhost:8000/v1"

    state = MagicMock()
    state.load_config.return_value = cfg
    state.config = cfg

    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    from unittest import mock

    with mock.patch("miqi.config.loader.save_config"):
        result = await providers_update_handler(
            "r1",
            {"provider_name": "vllm", "api_base": "http://localhost:9000/v1"},
            "client-1", None, registry,
        )

    assert result["result"]["saved"] is True
    # Default model was claude (unusable — no anthropic key); saving the
    # local provider's base must switch to its test model.
    assert state.config.agents.defaults.model == "meta-llama/Llama-3.1-8B-Instruct"


@pytest.mark.asyncio
async def test_providers_update_local_provider_api_key_counts_configured():
    """A local provider with only an api_key set is still usable — the
    auto-switch must NOT fire when it holds the current default model."""
    from unittest.mock import MagicMock

    from miqi.config.schema import Config

    cfg = Config()
    cfg.agents.defaults.model = "meta-llama/Llama-3.1-8B-Instruct"
    cfg.providers.vllm.api_key = "local-key"

    state = MagicMock()
    state.load_config.return_value = cfg
    state.config = cfg

    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    from unittest import mock

    with mock.patch("miqi.config.loader.save_config"):
        await providers_update_handler(
            "r1",
            {"provider_name": "deepseek", "api_key": "sk-ds-9876543210"},
            "client-1", None, registry,
        )

    # vllm (local, api_key-only) holds the default model — it is
    # usable, so the model must stay untouched.
    assert state.config.agents.defaults.model == "meta-llama/Llama-3.1-8B-Instruct"


@pytest.mark.asyncio
async def test_default_api_base_without_key_is_not_usable():
    """A standard provider with only the auto-filled default api_base (no
    api_key — key saved then cleared) must NOT count as configured. The
    auto-switch must fire when the current default model belongs to it."""
    from unittest.mock import MagicMock

    from miqi.config.schema import Config

    cfg = Config()
    cfg.agents.defaults.model = "anthropic/claude-opus-4-5"
    # Simulate: key was saved (auto-filling default api_base), then cleared
    cfg.providers.anthropic.api_base = "https://api.anthropic.com"
    cfg.providers.anthropic.api_key = ""

    state = MagicMock()
    state.load_config.return_value = cfg
    state.config = cfg

    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    from unittest import mock

    with mock.patch("miqi.config.loader.save_config"):
        await providers_update_handler(
            "r1",
            {"provider_name": "deepseek", "api_key": "sk-ds-9876543210"},
            "client-1", None, registry,
        )

    # anthropic has no key — only a default endpoint — so the default
    # model must switch to deepseek's.
    assert state.config.agents.defaults.model == "deepseek-v4-flash"
