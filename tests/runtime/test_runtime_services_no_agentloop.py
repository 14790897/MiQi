"""Audit: RuntimeServices carries model config via RuntimeModelSettings (Phase 48)."""


def test_runtime_services_uses_model_settings(fake_config, fake_provider, tmp_path):
    """RuntimeServices.from_config() must produce RuntimeModelSettings from agent defaults."""
    from miqi.runtime.services import RuntimeModelSettings, RuntimeServices

    services = RuntimeServices.from_config(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-model-settings",
        workspace=tmp_path,
    )

    assert services.model_settings is not None
    assert isinstance(services.model_settings, RuntimeModelSettings)
    assert services.model_settings.model == fake_config.agents.defaults.model
    assert services.model_settings.temperature == fake_config.agents.defaults.temperature
    assert services.model_settings.max_tokens == fake_config.agents.defaults.max_tokens
    assert not hasattr(services, "agent_loop")


def test_runtime_services_has_no_agentloop_field(fake_config, fake_provider, tmp_path):
    """RuntimeServices must not have an agent_loop attribute (no compat shim)."""
    from miqi.runtime.services import RuntimeServices

    services = RuntimeServices.from_config(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-no-agentloop",
        workspace=tmp_path,
    )

    assert not hasattr(services, "agent_loop")
    assert services.tool_registry is not None
    assert services.turn_runner is not None
