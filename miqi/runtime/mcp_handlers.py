"""MCP handlers for AppServer dispatch.

Phase 35.4: Migrates mcp.list, mcp.upsert, and mcp.delete from bridge
legacy handlers to AppServer async handlers.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError


async def mcp_list_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """List all configured MCP servers."""
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")

    config = state.load_config()
    servers = config.tools.mcp_servers or {}
    return {"result": {
        "servers": [
            {"name": name, **srv.model_dump()}
            for name, srv in servers.items()
        ],
    }}


async def mcp_upsert_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Create or update an MCP server entry by name."""
    from miqi.config.schema import MCPServerConfig
    from miqi.config.loader import save_config

    name = str(params.get("name", "")).strip()
    if not name:
        raise AppServerError("name is required", code="INVALID_PARAMS")

    # Build params dict without 'name' key for MCPServerConfig
    cfg_params = {k: v for k, v in params.items() if k != "name"}
    try:
        server_cfg = MCPServerConfig(**cfg_params)
    except Exception as exc:
        raise AppServerError(str(exc), code="INVALID_PARAMS") from exc

    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")

    config = state.load_config()
    if config.tools.mcp_servers is None:
        config.tools.mcp_servers = {}
    config.tools.mcp_servers[name] = server_cfg
    save_config(config)
    state.config = config

    return {"result": {"ok": True}}


async def mcp_delete_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Remove an MCP server entry by name."""
    from miqi.config.loader import save_config

    name = str(params.get("name", "")).strip()

    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")

    config = state.load_config()
    if config.tools.mcp_servers and name in config.tools.mcp_servers:
        del config.tools.mcp_servers[name]
        save_config(config)
        state.config = config

    return {"result": {"ok": True}}
