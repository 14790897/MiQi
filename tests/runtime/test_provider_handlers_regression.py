"""Provider handler tests — #602 list 标注 + #835 后端收口.

#602 的「写自定义 key 自动切模型」用例已删除:后端收口(#835)移除了
providers.update 的自定义凭据写入路径,该行为不再存在。替换为收口回归测试,
断言自配凭据被拒绝、model-only 覆盖仍可用。
"""

from __future__ import annotations

import pytest

from miqi.runtime.app_server import AppServerError, ClientSessionRegistry
from miqi.runtime.provider_handlers import (
    providers_deactivate_handler,
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


# ── providers.list（保留）─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_providers_list_does_not_mislabel_global_model_as_deepseek_model():
    """providers.list must not report the claude default as deepseek's configured_model."""
    registry = _make_registry("anthropic/claude-opus-4-5", deepseek="sk-ds-1234567890")

    result = await providers_list_handler("r1", {}, "client-1", None, registry)
    providers = {p["name"]: p for p in result["result"]["providers"]}

    deepseek = providers["deepseek"]
    assert deepseek["configured"] is True
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


# ── 后端收口（#835）：providers.update 拒绝自配凭据 ─────────────────────────


@pytest.mark.asyncio
async def test_providers_update_rejects_custom_api_key():
    """后端收口：providers.update 拒绝非空 api_key。"""
    registry = _make_registry("deepseek/deepseek-v4-flash")

    with pytest.raises(AppServerError) as exc:
        await providers_update_handler(
            "r1",
            {"provider_name": "deepseek", "api_key": "sk-ds-custom"},
            "client-1", None, registry,
        )
    assert exc.value.code == "NOT_SUPPORTED"


@pytest.mark.asyncio
async def test_providers_update_rejects_custom_api_base():
    """后端收口：providers.update 拒绝非空 api_base。"""
    registry = _make_registry("deepseek/deepseek-v4-flash")

    with pytest.raises(AppServerError) as exc:
        await providers_update_handler(
            "r1",
            {"provider_name": "deepseek", "api_base": "https://evil.example.com/v1"},
            "client-1", None, registry,
        )
    assert exc.value.code == "NOT_SUPPORTED"


@pytest.mark.asyncio
async def test_providers_update_model_only_still_works():
    """后端收口：providers.update 仍支持 model 覆盖（内置激活流程用）。"""
    from unittest import mock

    registry = _make_registry("deepseek/deepseek-v4-flash")
    state = registry.bridge_context["state"]

    with mock.patch("miqi.config.loader.save_config"):
        result = await providers_update_handler(
            "r1",
            {"provider_name": "deepseek", "model": "deepseek/deepseek-v4-flash"},
            "client-1", None, registry,
        )

    assert result["result"]["saved"] is True
    assert state.config.agents.defaults.model == "deepseek/deepseek-v4-flash"


@pytest.mark.asyncio
async def test_providers_deactivate_clears_builtin_activation():
    """后端收口（#835）：providers.deactivate 清空 api_key 与 activation 标记。"""
    from unittest import mock

    registry = _make_registry("deepseek/deepseek-v4-flash", deepseek="sk-ds-1234567890")
    state = registry.bridge_context["state"]
    config = state.load_config()
    # 模拟已激活标记
    config.desktop = {"providerActivation": {"deepseek": {"builtin": True}}}

    with mock.patch("miqi.config.loader.save_config"):
        result = await providers_deactivate_handler(
            "r1",
            {"provider_name": "deepseek"},
            "client-1", None, registry,
        )

    assert result["result"]["deactivated"] is True
    assert config.providers.deepseek.api_key == ""
    assert config.desktop.get("providerActivation", {}).get("deepseek") is None
