"""MCP runtime — runtime-owned MCP/plugin adapter.

Wraps PluginManager to provide a runtime-scoped view of active MCP
servers so the frontend and turn runner don't need to reach around
into the plugin layer directly.
"""

from __future__ import annotations

from typing import Any


class McpRuntime:
    """Runtime-owned MCP/plugin adapter.

    Provides a stable API for listing active MCP servers, so the
    frontend and other runtime components don't need to know about
    PluginManager internals.
    """

    def __init__(self, *, plugin_manager: Any | None):
        self.plugin_manager = plugin_manager

    def list_active_servers(self) -> list[dict[str, Any]]:
        """Return a list of active MCP server configs.

        Delegates to PluginManager.get_mcp_servers() when available.
        Returns an empty list when no plugin manager is configured.
        """
        if self.plugin_manager is None:
            return []
        fn = getattr(self.plugin_manager, "get_mcp_servers", None)
        if fn is None:
            return []
        return list(fn())
