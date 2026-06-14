"""Codex-style plugin and marketplace AppServer handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.runtime.app_server import AppServer, AppServerError, get_bridge_context
from miqi.runtime.plugin_catalog import PluginCatalogRuntime
from miqi.runtime.plugin_protocol import MarketplaceView


def _catalog(registry: Any) -> PluginCatalogRuntime:
    pm = get_bridge_context(registry, "plugin_manager", None)
    if pm is None:
        raise AppServerError("Plugin manager not initialized", code="INTERNAL")
    marketplaces_dir = Path(get_bridge_context(registry, "marketplaces_dir", Path.home() / ".miqi" / "marketplaces"))
    catalog = get_bridge_context(registry, "plugin_catalog", None)
    if catalog is None:
        catalog = PluginCatalogRuntime(plugin_manager=pm, marketplaces_dir=marketplaces_dir)
        registry.bridge_context["plugin_catalog"] = catalog
    return catalog


def register_plugin_app_handlers(server: AppServer) -> None:
    async def _plugin_list(request_id, params, client_id, session_id, registry):
        catalog = _catalog(registry)
        return {"result": {
            "marketplaces": [m.to_dict() for m in catalog.list_marketplaces()],
            "plugins": [p.to_dict() for p in catalog.list_plugins()],
            "featuredPluginIds": [],
            "marketplaceLoadErrors": [],
        }}

    async def _plugin_installed(request_id, params, client_id, session_id, registry):
        catalog = _catalog(registry)
        return {"result": {
            "plugins": [p.to_dict() for p in catalog.list_installed()],
        }}

    async def _plugin_read(request_id, params, client_id, session_id, registry):
        catalog = _catalog(registry)
        try:
            detail = catalog.read_plugin(
                plugin_name=params.get("pluginName") or params.get("plugin_name") or params.get("name"),
                marketplace_name=params.get("marketplaceName") or params.get("marketplace_name") or "local",
            )
        except KeyError as exc:
            raise AppServerError("Plugin not found", code="NOT_FOUND") from exc
        return {"result": {"plugin": detail.to_dict()}}

    async def _plugin_skill_read(request_id, params, client_id, session_id, registry):
        catalog = _catalog(registry)
        try:
            content = catalog.read_plugin_skill(
                plugin_name=params.get("pluginName") or params.get("plugin_name"),
                marketplace_name=params.get("marketplaceName") or params.get("marketplace_name") or "local",
                skill_name=params.get("skillName") or params.get("skill_name"),
            )
        except (KeyError, ValueError) as exc:
            raise AppServerError("Plugin skill not found", code="NOT_FOUND") from exc
        return {"result": {"content": content}}

    async def _plugin_install(request_id, params, client_id, session_id, registry):
        pm = get_bridge_context(registry, "plugin_manager", None)
        if pm is None:
            raise AppServerError("Plugin manager not initialized", code="INTERNAL")
        name = params.get("pluginName") or params.get("pluginId") or params.get("name")
        source = params.get("source") or params.get("url")
        if not name or not source:
            raise AppServerError("pluginName and source are required", code="INVALID_PARAMS")
        try:
            plugin = pm.install_plugin(str(name).split("@")[0], str(source))
        except ValueError as exc:
            raise AppServerError("Plugin installation rejected", code="INVALID_PARAMS") from exc
        registry.bridge_context.pop("plugin_catalog", None)
        return {"result": {"plugin": {"pluginId": f"{plugin.manifest.name}@local", "name": plugin.manifest.name}}}

    async def _plugin_uninstall(request_id, params, client_id, session_id, registry):
        pm = get_bridge_context(registry, "plugin_manager", None)
        if pm is None:
            raise AppServerError("Plugin manager not initialized", code="INTERNAL")
        raw = params.get("pluginId") or params.get("pluginName") or params.get("name")
        if not raw:
            raise AppServerError("pluginId is required", code="INVALID_PARAMS")
        name = str(raw).split("@")[0]
        removed = pm.uninstall_plugin(name)
        registry.bridge_context.pop("plugin_catalog", None)
        return {"result": {"removed": bool(removed), "pluginId": raw}}

    async def _marketplace_add(request_id, params, client_id, session_id, registry):
        catalog = _catalog(registry)
        name = str(params.get("name") or "").strip()
        source = str(params.get("source") or "").strip()
        if not name or not source:
            raise AppServerError("name and source are required", code="INVALID_PARAMS")
        view = MarketplaceView(
            name=name,
            display_name=name.replace("-", " ").title(),
            source=source,
            path=None,
            load_errors=[],
        )
        catalog._marketplaces[name] = view
        return {"result": {"marketplace": view.to_dict(), "alreadyPresent": False}}

    async def _marketplace_remove(request_id, params, client_id, session_id, registry):
        catalog = _catalog(registry)
        name = str(params.get("name") or params.get("marketplaceName") or "").strip()
        removed = name in catalog._marketplaces
        if name != "local":
            catalog._marketplaces.pop(name, None)
        return {"result": {"removed": removed, "marketplaceName": name}}

    async def _marketplace_upgrade(request_id, params, client_id, session_id, registry):
        catalog = _catalog(registry)
        name = params.get("marketplaceName")
        selected = [str(name)] if name else [m.name for m in catalog.list_marketplaces()]
        return {"result": {"selectedMarketplaces": selected, "errors": []}}

    server.register_method("plugin/list", _plugin_list)
    server.register_method("plugin/installed", _plugin_installed)
    server.register_method("plugin/read", _plugin_read)
    server.register_method("plugin/skill/read", _plugin_skill_read)
    server.register_method("plugin/install", _plugin_install)
    server.register_method("plugin/uninstall", _plugin_uninstall)
    server.register_method("marketplace/add", _marketplace_add)
    server.register_method("marketplace/remove", _marketplace_remove)
    server.register_method("marketplace/upgrade", _marketplace_upgrade)
