"""Tests for config loader migrations — custom/* model reset (#929 / #933)."""

from __future__ import annotations

from miqi.config.loader import _migrate_config


def test_migrate_resets_custom_model_to_configured_provider_model():
    """遗留 custom/* 默认模型应重置为已配置 provider 的测试模型，
    而不是无条件写无凭据的出厂默认（#933 review）。"""
    data = {
        "agents": {"defaults": {"model": "custom/my-model"}},
        "providers": {"deepseek": {"api_key": "sk-ds-1234567890"}},
    }
    migrated = _migrate_config(data)
    assert migrated["agents"]["defaults"]["model"] == "deepseek/deepseek-v4-flash"


def test_migrate_resets_custom_model_to_gateway_model():
    """已配置网关时重置为网关可路由的完整模型 id（网关在注册表最前）。"""
    data = {
        "agents": {"defaults": {"model": "custom/default"}},
        "providers": {"openrouter": {"api_key": "sk-or-1234567890"}},
    }
    migrated = _migrate_config(data)
    assert migrated["agents"]["defaults"]["model"] == "anthropic/claude-opus-4-5"


def test_migrate_defaults_to_v4_flash_without_credentials():
    """没有任何可用凭据时回退到产品默认 deepseek/deepseek-v4-flash
    （#835 收口后唯一内置模型）。"""
    data = {"agents": {"defaults": {"model": "custom/x"}}}
    migrated = _migrate_config(data)
    assert migrated["agents"]["defaults"]["model"] == "deepseek/deepseek-v4-flash"


def test_migrate_ignores_camelcase_provider_keys():
    """配置 JSON 可能是 camelCase 键，迁移需兼容（#933 review）。"""
    data = {
        "agents": {"defaults": {"model": "custom/x"}},
        "providers": {"deepseek": {"apiKey": "sk-ds-1234567890"}},
    }
    migrated = _migrate_config(data)
    assert migrated["agents"]["defaults"]["model"] == "deepseek/deepseek-v4-flash"


def test_migrate_leaves_other_models_untouched():
    data = {"agents": {"defaults": {"model": "deepseek/deepseek-v4-flash"}}}
    migrated = _migrate_config(data)
    assert migrated["agents"]["defaults"]["model"] == "deepseek/deepseek-v4-flash"
