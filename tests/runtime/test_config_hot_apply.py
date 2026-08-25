"""RuntimeServices.apply_config_update hot-apply tests (issue #789)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from miqi.config.schema import Config
from miqi.runtime.context_runtime import ContextRuntime
from miqi.runtime.services import RuntimeServices


def _make_services(provider=None):
    services = RuntimeServices(
        session_id="test:1",
        workspace=Path("."),
        bus=None,
        provider=provider,
        event_emitter=None,
        model_settings=None,
        tool_registry=None,
        orchestrator=SimpleNamespace(permissions=SimpleNamespace(approval_bypass=None)),
        agent_registry=None,
        agent_control=None,
        tool_runtime=None,
        context_runtime=None,
        turn_runner=SimpleNamespace(_provider=provider, _max_iterations=500),
        plugin_manager=None,
    )
    services.session_state = SimpleNamespace(config_snapshot=None)
    return services


def test_updates_model_settings_and_snapshot():
    services = _make_services()
    cfg = Config()
    cfg.agents.defaults.model = "deepseek/deepseek-chat"
    cfg.agents.defaults.temperature = 0.7
    cfg.agents.defaults.max_tokens = 2048

    result = services.apply_config_update(cfg)

    assert services.model_settings.model == "deepseek/deepseek-chat"
    assert services.model_settings.temperature == 0.7
    assert services.model_settings.max_tokens == 2048
    assert services.model_settings.max_tool_result_chars == cfg.agents.defaults.max_tool_result_chars
    assert services.session_state.config_snapshot is cfg
    assert services.turn_runner._max_iterations == cfg.agents.defaults.max_tool_iterations
    # No API key configured → make_provider raises → old provider retained.
    assert result["provider_rebuilt"] is False


def test_rebuilds_provider_when_configured():
    old_provider = object()
    services = _make_services(provider=old_provider)
    cfg = Config()
    cfg.providers.deepseek.api_key = "sk-test"

    result = services.apply_config_update(cfg)

    assert result["provider_rebuilt"] is True
    assert services.provider is not old_provider
    assert services.turn_runner._provider is services.provider


def test_failed_provider_rebuild_keeps_old_provider():
    old_provider = object()
    services = _make_services(provider=old_provider)
    cfg = Config()  # no api key → make_provider raises ValueError

    result = services.apply_config_update(cfg)

    assert result["provider_rebuilt"] is False
    assert services.provider is old_provider
    # Other fields still hot-applied (no half-updated state).
    assert services.model_settings is not None
    assert services.session_state.config_snapshot is cfg


def test_updates_approval_bypass():
    services = _make_services()
    cfg = Config()
    cfg.approvals.bypass_all = True

    services.apply_config_update(cfg)

    bypass = services.orchestrator.permissions.approval_bypass
    assert bypass.bypass_all is True


def test_updates_permanent_allowlist():
    from miqi.agent.command_approval import get_permanent_allowlist, replace_permanent_allowlist

    replace_permanent_allowlist(set())  # reset global state before the test
    try:
        services = _make_services()
        cfg = Config()
        cfg.agents.permanent_approvals = ["pattern-a", "pattern-b"]

        services.apply_config_update(cfg)

        assert get_permanent_allowlist() == {"pattern-a", "pattern-b"}
    finally:
        replace_permanent_allowlist(set())  # restore global state


def test_allowlist_not_refreshed_when_opt_out():
    """An unrelated save must not clobber runtime-approved patterns."""
    from miqi.agent.command_approval import (
        approve_permanent,
        get_permanent_allowlist,
        replace_permanent_allowlist,
    )

    replace_permanent_allowlist(set())
    try:
        approve_permanent("user-approved-at-runtime")
        services = _make_services()
        cfg = Config()  # permanent_approvals is empty in the new config

        services.apply_config_update(cfg, refresh_permanent_allowlist=False)

        # The runtime-approved pattern survives the unrelated save.
        assert "user-approved-at-runtime" in get_permanent_allowlist()
    finally:
        replace_permanent_allowlist(set())


def test_context_compressor_closure_rebuilt_with_new_provider():
    """Compaction must use a NEW provider closure after a hot apply."""
    services = _make_services()
    services.context_runtime = ContextRuntime(
        llm_call_fn=lambda msgs, model: "old",
        context_limit_chars=12345,
    )
    old_compressor = services.context_runtime._compressor

    cfg = Config()
    cfg.providers.deepseek.api_key = "sk-test"
    services.apply_config_update(cfg)

    new_compressor = services.context_runtime._compressor
    assert new_compressor is not old_compressor  # rebuilt, not mutated
    assert new_compressor.context_limit_chars == 12345  # config preserved
    # The closure itself was replaced (reads services.provider at call time).
    assert new_compressor._llm_call is not old_compressor._llm_call
