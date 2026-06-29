from unittest.mock import MagicMock

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.mcp_app_handlers import register_mcp_app_handlers
from miqi.runtime.mcp_status_runtime import McpStatusRuntime


@pytest.mark.asyncio
async def test_mcp_server_status_list_returns_servers():
    registry = ClientSessionRegistry()
    runtime = McpStatusRuntime()
    runtime.replace_config_servers({"server-a": {"command": "echo"}})
    registry.bridge_context["mcp_status_runtime"] = runtime
    server = AppServer(registry)
    register_mcp_app_handlers(server)

    response = await server.dispatch("1", "mcpServerStatus/list", {}, "client-1", None)
    assert response["result"]["servers"][0]["name"] == "server-a"


@pytest.mark.asyncio
async def test_mcp_resource_read_not_connected_is_safe():
    registry = ClientSessionRegistry()
    registry.bridge_context["mcp_status_runtime"] = McpStatusRuntime()
    server = AppServer(registry)
    register_mcp_app_handlers(server)

    response = await server.dispatch(
        "1", "mcpServer/resource/read",
        {"server": "missing", "uri": "resource://x"},
        "client-1", None,
    )
    assert response["code"] == "NOT_CONNECTED"


@pytest.mark.asyncio
async def test_config_mcp_server_reload_refreshes_statuses():
    registry = ClientSessionRegistry()
    runtime = McpStatusRuntime()
    registry.bridge_context["mcp_status_runtime"] = runtime
    state = MagicMock()
    cfg = MagicMock()
    cfg.tools.mcp_servers = {"server-a": MagicMock(model_dump=lambda: {"command": "echo"})}
    state.load_config.return_value = cfg
    registry.bridge_context["state"] = state
    server = AppServer(registry)
    register_mcp_app_handlers(server)

    response = await server.dispatch("1", "config/mcpServer/reload", {}, "client-1", None)
    assert response["result"] == {}
    assert runtime.list_statuses()[0].name == "server-a"
