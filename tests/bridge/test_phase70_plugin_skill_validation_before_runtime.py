from __future__ import annotations

import pytest

from miqi.runtime.app_server import AppServer, AppServerError, ClientSessionRegistry
from miqi.runtime.plugin_app_handlers import register_plugin_app_handlers
from miqi.runtime.skills_app_handlers import register_skills_app_handlers


@pytest.mark.asyncio
async def test_plugin_read_bad_params_invalid_before_catalog():
    server = AppServer(ClientSessionRegistry())
    register_plugin_app_handlers(server)
    server.registry.bridge_context = {}

    with pytest.raises(AppServerError) as exc:
        await server._dispatch_inner("req", "plugin/read", {"pluginName": 123}, "client", None)

    assert exc.value.code == "INVALID_PARAMS"
    await server.stop()


@pytest.mark.asyncio
async def test_plugin_install_missing_source_invalid_before_manager():
    server = AppServer(ClientSessionRegistry())
    register_plugin_app_handlers(server)
    server.registry.bridge_context = {}

    with pytest.raises(AppServerError) as exc:
        await server._dispatch_inner("req", "plugin/install", {"pluginName": "p"}, "client", None)

    assert exc.value.code == "INVALID_PARAMS"
    await server.stop()


@pytest.mark.asyncio
async def test_marketplace_add_empty_name_invalid_before_catalog():
    server = AppServer(ClientSessionRegistry())
    register_plugin_app_handlers(server)
    server.registry.bridge_context = {}

    with pytest.raises(AppServerError) as exc:
        await server._dispatch_inner("req", "marketplace/add", {"name": "", "source": "s"}, "client", None)

    assert exc.value.code == "INVALID_PARAMS"
    await server.stop()


@pytest.mark.asyncio
async def test_extra_roots_set_string_roots_invalid_before_workspace():
    server = AppServer(ClientSessionRegistry())
    register_skills_app_handlers(server)
    server.registry.bridge_context = {}

    with pytest.raises(AppServerError) as exc:
        await server._dispatch_inner("req", "skills/extraRoots/set", {"roots": "C:/x"}, "client", None)

    assert exc.value.code == "INVALID_PARAMS"
    await server.stop()


@pytest.mark.asyncio
async def test_hooks_list_string_cwds_invalid_before_workspace():
    server = AppServer(ClientSessionRegistry())
    register_skills_app_handlers(server)
    server.registry.bridge_context = {}

    with pytest.raises(AppServerError) as exc:
        await server._dispatch_inner("req", "hooks/list", {"cwds": "C:/x"}, "client", None)

    assert exc.value.code == "INVALID_PARAMS"
    await server.stop()
