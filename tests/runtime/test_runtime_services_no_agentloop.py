"""Audit test: RuntimeServices must not construct AgentLoop (Phase 22)."""

import pytest


def test_runtime_services_does_not_construct_agent_loop(monkeypatch, fake_config, fake_provider, tmp_path):
    """RuntimeServices.from_config() must not call AgentLoop(...)."""
    import miqi.agent.loop
    from miqi.runtime.services import RuntimeServices

    def fail_agent_loop(*args, **kwargs):
        raise AssertionError("RuntimeServices must not construct AgentLoop")

    monkeypatch.setattr(miqi.agent.loop, "AgentLoop", fail_agent_loop)

    services = RuntimeServices.from_config(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-no-agentloop",
        workspace=tmp_path,
    )

    assert services.tool_registry is not None
    assert services.turn_runner is not None


def test_runtime_services_has_compat_agent_loop(fake_config, fake_provider, tmp_path):
    """RuntimeServices.agent_loop must be a RuntimeAgentLoopCompat, not AgentLoop."""
    from miqi.runtime.services import RuntimeAgentLoopCompat, RuntimeServices

    services = RuntimeServices.from_config(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-compat",
        workspace=tmp_path,
    )

    assert isinstance(services.agent_loop, RuntimeAgentLoopCompat)
    assert services.agent_loop.model is not None
    assert services.agent_loop.temperature is not None
    assert services.agent_loop.max_tokens is not None
    # compat must have stop() and close_mcp()
    assert services.agent_loop.stop() is None
    import asyncio
    result = asyncio.run(services.agent_loop.close_mcp())
    assert result is None
