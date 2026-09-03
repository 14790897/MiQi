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
    providers_test_handler,
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


@pytest.mark.asyncio
async def test_providers_update_rejects_custom_provider_name():
    """#929：providers.update 按运行时注册表校验 provider_name。

    ProvidersConfig 存储 schema 仍保留 custom 字段，但工厂已移除 custom
    provider —— 用 schema 校验会放行一个运行时无法解析的默认模型。
    """
    from unittest import mock

    registry = _make_registry("deepseek/deepseek-v4-flash")

    with mock.patch("miqi.config.loader.save_config"):
        with pytest.raises(AppServerError) as exc:
            await providers_update_handler(
                "r1",
                {"provider_name": "custom", "model": "custom/default"},
                "client-1", None, registry,
            )
    assert exc.value.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_providers_deactivate_rejects_non_builtin_provider():
    """只有内置 provider 支持取消激活。"""
    registry = _make_registry("anthropic/claude-opus-4-5", anthropic="sk-an-1234567890")

    with pytest.raises(AppServerError) as exc:
        await providers_deactivate_handler(
            "r1",
            {"provider_name": "anthropic"},
            "client-1", None, registry,
        )
    assert exc.value.code == "NOT_SUPPORTED"


# ── 内置密钥端点收口（#929）：test 不走历史遗留 api_base ─────────────────────


def _builtin_activated_registry(base: str | None) -> ClientSessionRegistry:
    registry = _make_registry("deepseek/deepseek-v4-flash", deepseek="builtin-secret")
    cfg = registry.bridge_context["state"].load_config()
    cfg.providers.deepseek.api_base = base
    cfg.desktop = {"providerActivation": {"deepseek": {"builtin": True}}}
    return registry


@pytest.mark.asyncio
async def test_providers_test_ignores_legacy_api_base_when_builtin_activated():
    """内置激活时测试必须走官方端点，忽略历史遗留的自定义 api_base。"""
    from unittest import mock

    registry = _builtin_activated_registry("https://evil.example.com/v1")
    response = mock.MagicMock()
    response.finish_reason = "stop"
    response.error_kind = None

    with mock.patch("miqi.config.loader.save_config"), mock.patch(
        "miqi.providers.openai_provider.OpenAIProvider"
    ) as provider_cls:
        provider_cls.return_value.chat = mock.AsyncMock(return_value=response)
        result = await providers_test_handler(
            "r1",
            {"provider_name": "deepseek"},
            "client-1", None, registry,
        )

    assert result["result"]["ok"] is True
    kwargs = provider_cls.call_args.kwargs
    # provider 构造回落 spec.default_api_base（官方端点）
    assert kwargs["api_base"] is None


@pytest.mark.asyncio
async def test_providers_test_keeps_saved_base_without_builtin_activation():
    """未内置激活时保留历史行为：使用配置里保存的 api_base。"""
    from unittest import mock

    registry = _make_registry("deepseek/deepseek-v4-flash", deepseek="sk-legacy-1234567890")
    cfg = registry.bridge_context["state"].load_config()
    cfg.providers.deepseek.api_base = "https://legacy.example.com/v1"
    response = mock.MagicMock()
    response.finish_reason = "stop"
    response.error_kind = None

    with mock.patch("miqi.config.loader.save_config"), mock.patch(
        "miqi.providers.openai_provider.OpenAIProvider"
    ) as provider_cls:
        provider_cls.return_value.chat = mock.AsyncMock(return_value=response)
        result = await providers_test_handler(
            "r1",
            {"provider_name": "deepseek"},
            "client-1", None, registry,
        )

    assert result["result"]["ok"] is True
    kwargs = provider_cls.call_args.kwargs
    assert kwargs["api_base"] == "https://legacy.example.com/v1"


@pytest.mark.asyncio
async def test_providers_update_rejects_unresolvable_model():
    """#929：providers.update 拒绝运行时无法解析的模型值。"""
    from unittest import mock

    registry = _make_registry("deepseek/deepseek-v4-flash")

    with mock.patch("miqi.config.loader.save_config"):
        with pytest.raises(AppServerError) as exc:
            await providers_update_handler(
                "r1",
                {"provider_name": "deepseek", "model": "custom/default"},
                "client-1", None, registry,
            )
    assert exc.value.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_providers_deactivate_rejects_without_activation_marker():
    """#929：没有内置激活标记时拒绝取消激活，避免误清历史遗留的自配 key。"""
    registry = _make_registry("deepseek/deepseek-v4-flash", deepseek="sk-legacy-1234567890")

    with pytest.raises(AppServerError) as exc:
        await providers_deactivate_handler(
            "r1",
            {"provider_name": "deepseek"},
            "client-1", None, registry,
        )
    assert exc.value.code == "NOT_ACTIVATED"
