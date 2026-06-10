"""Tests for CapabilityResolver (Phase 13.4)."""

import pytest


@pytest.fixture
def fake_tool_registry():
    from unittest.mock import MagicMock

    registry = MagicMock()
    registry.get_definitions.return_value = [
        {"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {}}},
        {"type": "function", "function": {"name": "exec", "description": "Execute command", "parameters": {}}},
        {"type": "function", "function": {"name": "docx_read", "description": "Read docx", "parameters": {}}},
        {"type": "function", "function": {"name": "web_search", "description": "Search web", "parameters": {}}},
    ]
    return registry


@pytest.fixture
def fake_plugin_manager():
    from unittest.mock import MagicMock

    class _FakePlugin:
        class manifest:
            name = "my-plugin"
        status = "active"

    pm = MagicMock()
    pm.list_plugins.return_value = [_FakePlugin()]
    pm.get_mcp_servers.return_value = [
        {"name": "test-server", "command": "echo", "args": ["hello"]},
    ]
    return pm


@pytest.fixture
def fake_agent_metadata():
    from unittest.mock import MagicMock

    meta = MagicMock()
    meta.name = "code-agent"
    meta.available_tools = ["read_file", "exec", "web_search"]
    return meta


def test_capability_resolver_filters_tools_by_agent_role(
    fake_tool_registry, fake_plugin_manager, fake_agent_metadata,
):
    from miqi.runtime.capabilities import CapabilityResolver

    resolver = CapabilityResolver(
        tool_registry=fake_tool_registry,
        plugin_manager=fake_plugin_manager,
    )

    caps = resolver.resolve(agent_metadata=fake_agent_metadata)

    assert caps.tool_definitions
    assert all(
        item["function"]["name"] in fake_agent_metadata.available_tools
        for item in caps.tool_definitions
    )
    # code-agent should NOT get docx_read
    tool_names = {t["function"]["name"] for t in caps.tool_definitions}
    assert "docx_read" not in tool_names


def test_capability_resolver_includes_active_plugins(fake_tool_registry, fake_plugin_manager, fake_agent_metadata):
    from miqi.runtime.capabilities import CapabilityResolver

    resolver = CapabilityResolver(
        tool_registry=fake_tool_registry,
        plugin_manager=fake_plugin_manager,
    )

    caps = resolver.resolve(agent_metadata=fake_agent_metadata)

    assert caps.plugins == ["my-plugin"]
    assert len(caps.mcp_servers) == 1
    assert caps.mcp_servers[0]["name"] == "test-server"


def test_capability_resolver_works_without_plugin_manager(fake_tool_registry, fake_agent_metadata):
    from miqi.runtime.capabilities import CapabilityResolver

    resolver = CapabilityResolver(
        tool_registry=fake_tool_registry,
        plugin_manager=None,
    )

    caps = resolver.resolve(agent_metadata=fake_agent_metadata)
    assert caps.plugins == []
    assert caps.mcp_servers == []
    assert caps.skills == []
    # Tools still work
    assert len(caps.tool_definitions) == 3  # read_file, exec, web_search
