"""Codex-style MCP AppServer handlers."""

from __future__ import annotations

from typing import Any

from miqi.runtime.app_server import AppServer, AppServerError, get_bridge_context, get_bridge_state
from miqi.runtime.mcp_status_runtime import McpStatusRuntime


def _runtime(registry: Any) -> McpStatusRuntime:
    rt = get_bridge_context(registry, "mcp_status_runtime", None)
    if rt is None:
        rt = McpStatusRuntime()
        registry.bridge_context["mcp_status_runtime"] = rt
    return rt


def register_mcp_app_handlers(server: AppServer) -> None:
    async def _status_list(request_id, params, client_id, session_id, registry):
        rt = _runtime(registry)
        thread_id = params.get("threadId") or params.get("thread_id")
        return {"result": {"servers": [s.to_dict() for s in rt.list_statuses(thread_id=thread_id)]}}

    async def _reload(request_id, params, client_id, session_id, registry):
        state = get_bridge_state(registry)
        cfg = state.load_config()
        servers = cfg.tools.mcp_servers or {}
        rt = _runtime(registry)
        rt.replace_config_servers(servers)
        plugin_manager = get_bridge_context(registry, "plugin_manager", None)
        if plugin_manager is not None and hasattr(plugin_manager, "get_mcp_servers"):
            rt.replace_plugin_servers(list(plugin_manager.get_mcp_servers()))
        return {"result": {}}

    async def _resource_read(request_id, params, client_id, session_id, registry):
        raise AppServerError("MCP server is not connected", code="NOT_CONNECTED", recoverable=True)

    async def _tool_call(request_id, params, client_id, session_id, registry):
        raise AppServerError("MCP tool call is not connected", code="NOT_CONNECTED", recoverable=True)

    server.register_method("mcpServerStatus/list", _status_list)
    server.register_method("config/mcpServer/reload", _reload)
    server.register_method("mcpServer/resource/read", _resource_read)
    server.register_method("mcpServer/tool/call", _tool_call)
