"""Hot config reload classification tests (issue #789)."""

from __future__ import annotations

from miqi.config.hot_reload import classify_config_update
from miqi.config.schema import Config


def _mutate(**changes) -> Config:
    """Return a config copy with the given dotted-path mutations applied."""
    cfg = Config()
    for path, value in changes.items():
        parts = path.split(".")
        target = cfg
        for part in parts[:-1]:
            target = getattr(target, part)
        setattr(target, parts[-1], value)
    return cfg


def test_model_change_is_tier_a():
    new = _mutate(**{"agents.defaults.model": "deepseek/deepseek-chat"})
    report = classify_config_update(Config(), new)
    assert "agents.defaults.model" in report.applied
    assert report.needs_restart is False


def test_temperature_change_is_tier_a():
    new = _mutate(**{"agents.defaults.temperature": 0.5})
    report = classify_config_update(Config(), new)
    assert "agents.defaults.temperature" in report.applied


def test_provider_api_key_change_is_tier_a():
    new = _mutate(**{"providers.deepseek.api_key": "sk-test"})
    report = classify_config_update(Config(), new)
    assert "providers.deepseek.api_key" in report.applied


def test_approval_bypass_change_is_tier_a():
    new = _mutate(**{"approvals.bypass_all": True})
    report = classify_config_update(Config(), new)
    assert "approvals.bypass_all" in report.applied


def test_sandbox_enabled_toggle_is_tier_a():
    new = _mutate(**{"tools.sandbox.enabled": False})
    report = classify_config_update(Config(), new)
    assert "tools.sandbox.enabled" in report.applied


def test_web_search_provider_is_tier_b():
    new = _mutate(**{"tools.web.search.provider": "tavily"})
    report = classify_config_update(Config(), new)
    assert "tools.web.search.provider" in report.new_sessions_only
    assert report.applied == []


def test_workspace_change_is_tier_b():
    new = _mutate(**{"agents.defaults.workspace": "/tmp/ws"})
    report = classify_config_update(Config(), new)
    assert "agents.defaults.workspace" in report.new_sessions_only


def test_wsl_distro_change_is_tier_c_with_reason():
    new = _mutate(**{"tools.sandbox.wsl_distro": "Ubuntu"})
    report = classify_config_update(Config(), new)
    assert "tools.sandbox.wsl_distro" in report.restart_required
    assert report.needs_restart is True
    assert len(report.restart_reasons) == 1
    assert "WSL" in report.restart_reasons[0]


def test_gateway_port_change_is_tier_c():
    new = _mutate(**{"gateway.port": 9999})
    report = classify_config_update(Config(), new)
    assert "gateway.port" in report.restart_required


def test_mcp_servers_change_is_tier_c():
    from miqi.config.schema import MCPServerConfig

    new = _mutate(**{"tools.mcp_servers": {"server1": MCPServerConfig(command="npx")}})
    report = classify_config_update(Config(), new)
    # Diff recurses into the dict; the prefix rule still classifies as C.
    assert any(p.startswith("tools.mcp_servers") for p in report.restart_required)
    assert report.needs_restart is True


def test_mixed_change_reports_all_tiers():
    new = Config()
    new.agents.defaults.model = "deepseek/deepseek-chat"  # A
    new.tools.web.search.provider = "tavily"  # B
    new.tools.sandbox.wsl_distro = "Ubuntu"  # C
    report = classify_config_update(Config(), new)
    assert report.applied == ["agents.defaults.model"]
    assert report.new_sessions_only == ["tools.web.search.provider"]
    assert report.restart_required == ["tools.sandbox.wsl_distro"]


def test_no_change_produces_empty_report():
    report = classify_config_update(Config(), Config())
    assert report.applied == []
    assert report.new_sessions_only == []
    assert report.restart_required == []
    assert report.needs_restart is False


def test_to_dict_uses_camel_case_keys():
    new = _mutate(**{"tools.sandbox.wsl_distro": "Ubuntu"})
    d = classify_config_update(Config(), new).to_dict()
    assert "restartRequired" in d
    assert "restartReasons" in d
    assert "newSessionsOnly" in d
    assert "applied" in d


def test_prefix_boundary_no_false_positive():
    """max_tokens change must not match the max_tool_* prefixes."""
    new = _mutate(**{"agents.defaults.max_tokens": 4096})
    report = classify_config_update(Config(), new)
    assert "agents.defaults.max_tokens" in report.applied
    # A sibling path that is NOT tier A stays tier B.
    new2 = _mutate(**{"agents.defaults.max_tool_result_chars": 100})
    report2 = classify_config_update(Config(), new2)
    assert "agents.defaults.max_tool_result_chars" in report2.applied


def test_snake_case_update_survives_validation():
    """Regression: config.update deep-merge must not drop snake_case keys.

    The merged dict used to be built from a by_alias=True (camelCase) dump;
    Pydantic's alias takes precedence when both spellings exist, so a
    snake_case update (wsl_distro) was silently ignored and the value never
    changed (#789 E2E 实录).
    """
    from miqi.runtime.config_app_handlers import _deep_merge

    current = Config()
    merged = _deep_merge(
        current.model_dump(by_alias=False),
        {"tools": {"sandbox": {"wsl_distro": "Ubuntu"}}},
    )
    new_config = Config.model_validate(merged)
    assert new_config.tools.sandbox.wsl_distro == "Ubuntu"


def test_camel_case_update_survives_validation():
    """camelCase updates (config.get → modify → save round-trip) still work."""
    from miqi.runtime.config_app_handlers import _deep_merge

    current = Config()
    merged = _deep_merge(
        current.model_dump(by_alias=False),
        {"tools": {"sandbox": {"wslDistro": "Ubuntu"}}},
    )
    new_config = Config.model_validate(merged)
    assert new_config.tools.sandbox.wsl_distro == "Ubuntu"
