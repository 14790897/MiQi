"""Codex-style MCP AppServer handlers."""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

from miqi.runtime.app_server import AppServer, AppServerError, get_bridge_context, get_bridge_state
from miqi.runtime.mcp_status_runtime import McpStatusRuntime


def _runtime(registry: Any) -> McpStatusRuntime:
    rt = get_bridge_context(registry, "mcp_status_runtime", None)
    if rt is None:
        rt = McpStatusRuntime()
        registry.bridge_context["mcp_status_runtime"] = rt
    return rt


def _import_kwp_mcp(plugin_path: Path) -> list[dict[str, Any]]:
    """Parse a KWP/Claude Code ``.mcp.json`` and return MiQi-format server entries.

    KWP format:
      {"mcpServers": {"<key>": {"type": "http", "url": "...", "oauth": {...}}}}

    MiQi format:
      {"name": "<key>", "url": "...", "headers": {"oauth_client_id": "..."}}
    """
    mcp_file = plugin_path / ".mcp.json"
    if not mcp_file.is_file():
        return []
    try:
        data = _json.loads(mcp_file.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError):
        return []

    servers: dict[str, Any] = data.get("mcpServers") or {}
    result: list[dict[str, Any]] = []
    for key, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        entry: dict[str, Any] = {"name": key}
        url = cfg.get("url", "")
        if url:
            entry["url"] = url
        oauth = cfg.get("oauth")
        if isinstance(oauth, dict):
            entry.setdefault("headers", {})
            cid = oauth.get("clientId", "")
            if cid:
                entry["headers"]["oauth_client_id"] = cid
        if cfg.get("type") == "http":
            entry["transport"] = "http"
        result.append(entry)
    return result


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

    async def _kwp_import_mcp(request_id, params, client_id, session_id, registry):
        """Import MCP servers from a KWP plugin's ``.mcp.json`` file.

        The caller provides ``plugin_name`` or ``plugin_path``.
        If ``merge`` is true (default), the servers are upserted into
        the runtime config.
        """
        plugin_name = params.get("plugin_name", "").strip()
        plugin_path_str = params.get("plugin_path", "").strip()
        merge = params.get("merge", True)

        if plugin_path_str:
            p = Path(plugin_path_str).expanduser().resolve()
        elif plugin_name:
            pm = get_bridge_context(registry, "plugin_manager", None)
            if pm is None:
                raise AppServerError(
                    "Plugin manager not available", code="INTERNAL",
                )
            plugin = pm.get_plugin(plugin_name)
            if plugin is None:
                raise AppServerError(
                    f"Plugin '{plugin_name}' not found", code="NOT_FOUND",
                )
            p = plugin.path
        else:
            raise AppServerError(
                "plugin_name or plugin_path is required", code="INVALID_PARAMS",
            )

        imported = _import_kwp_mcp(p)
        if merge and imported:
            state = get_bridge_state(registry)
            cfg = state.load_config()
            existing = dict(cfg.tools.mcp_servers or {})
            for srv in imported:
                name = srv.get("name", "")
                if name:
                    existing[name] = srv
            cfg.tools.mcp_servers = existing
            state.save_config(cfg)
            # Reload status runtime
            rt = _runtime(registry)
            rt.replace_config_servers(existing)

        return {"result": {"imported": imported, "merged": merge and len(imported) > 0}}

    server.register_method("mcpServerStatus/list", _status_list)
    server.register_method("config/mcpServer/reload", _reload)
    server.register_method("mcpServer/resource/read", _resource_read)
    server.register_method("mcpServer/tool/call", _tool_call)
    server.register_method("kwp/import-mcp-config", _kwp_import_mcp)
