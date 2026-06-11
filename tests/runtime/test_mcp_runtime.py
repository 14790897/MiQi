"""Tests for McpRuntime (Phase 21)."""

import pytest

from miqi.runtime.mcp_runtime import McpRuntime


@pytest.mark.asyncio
async def test_mcp_runtime_lists_active_servers():
    """McpRuntime delegates list_active_servers() to PluginManager."""
    plugin_manager = type("PM", (), {
        "get_mcp_servers": lambda self: [{"name": "server-a"}],
    })()
    runtime = McpRuntime(plugin_manager=plugin_manager)

    assert runtime.list_active_servers() == [{"name": "server-a"}]


@pytest.mark.asyncio
async def test_mcp_runtime_returns_empty_without_plugin_manager():
    """When plugin_manager is None, list_active_servers() returns []."""
    runtime = McpRuntime(plugin_manager=None)

    assert runtime.list_active_servers() == []


@pytest.mark.asyncio
async def test_mcp_runtime_returns_empty_when_no_method():
    """When plugin_manager has no get_mcp_servers, returns []."""
    plugin_manager = object()
    runtime = McpRuntime(plugin_manager=plugin_manager)

    assert runtime.list_active_servers() == []
