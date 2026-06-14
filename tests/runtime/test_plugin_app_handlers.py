import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.plugin_app_handlers import register_plugin_app_handlers
from miqi.skills.plugin_manager import PluginManager


def write_plugin(root: Path, name: str) -> None:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": name,
        "version": "1.0.0",
        "description": "Sample plugin",
        "author": "test",
        "mcp_servers": [{"name": "sample-mcp", "command": "echo"}],
        "skills": ["sample-skill"],
        "slash_commands": [],
    }), encoding="utf-8")
    skill_dir = plugin_dir / "skills" / "sample-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: sample-skill\n---\n# Sample\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_plugin_list_and_installed(tmp_path):
    user_dir = tmp_path / "plugins"
    write_plugin(user_dir, "sample")
    pm = PluginManager(user_dir, tmp_path / "system")
    await pm.discover()
    registry = ClientSessionRegistry()
    registry.bridge_context["plugin_manager"] = pm
    registry.bridge_context["marketplaces_dir"] = tmp_path / "marketplaces"
    server = AppServer(registry)
    register_plugin_app_handlers(server)

    listed = await server.dispatch("1", "plugin/list", {}, "client-1", None)
    installed = await server.dispatch("2", "plugin/installed", {}, "client-1", None)
    assert listed["result"]["marketplaces"][0]["name"] == "local"
    assert listed["result"]["plugins"][0]["pluginId"] == "sample@local"
    assert installed["result"]["plugins"][0]["mention"] == "plugin://sample@local"


@pytest.mark.asyncio
async def test_plugin_read_and_skill_read(tmp_path):
    user_dir = tmp_path / "plugins"
    write_plugin(user_dir, "sample")
    pm = PluginManager(user_dir, tmp_path / "system")
    await pm.discover()
    registry = ClientSessionRegistry()
    registry.bridge_context["plugin_manager"] = pm
    registry.bridge_context["marketplaces_dir"] = tmp_path / "marketplaces"
    server = AppServer(registry)
    register_plugin_app_handlers(server)

    detail = await server.dispatch(
        "1", "plugin/read",
        {"pluginName": "sample", "marketplaceName": "local"},
        "client-1", None,
    )
    skill = await server.dispatch(
        "2", "plugin/skill/read",
        {"pluginName": "sample", "marketplaceName": "local", "skillName": "sample-skill"},
        "client-1", None,
    )
    assert detail["result"]["plugin"]["pluginId"] == "sample@local"
    assert "# Sample" in skill["result"]["content"]


@pytest.mark.asyncio
async def test_marketplace_add_remove_upgrade_return_stable_shapes(tmp_path):
    pm = PluginManager(tmp_path / "plugins", tmp_path / "system")
    registry = ClientSessionRegistry()
    registry.bridge_context["plugin_manager"] = pm
    registry.bridge_context["marketplaces_dir"] = tmp_path / "marketplaces"
    server = AppServer(registry)
    register_plugin_app_handlers(server)

    added = await server.dispatch(
        "1", "marketplace/add",
        {"name": "local-debug", "source": str(tmp_path / "marketplace-source")},
        "client-1", None,
    )
    upgraded = await server.dispatch("2", "marketplace/upgrade", {}, "client-1", None)
    removed = await server.dispatch(
        "3", "marketplace/remove", {"name": "local-debug"}, "client-1", None,
    )
    assert added["result"]["marketplace"]["name"] == "local-debug"
    assert "selectedMarketplaces" in upgraded["result"]
    assert removed["result"]["removed"] is True


@pytest.mark.asyncio
async def test_plugin_read_not_found_is_sanitized(tmp_path):
    pm = PluginManager(tmp_path / "plugins", tmp_path / "system")
    registry = ClientSessionRegistry()
    registry.bridge_context["plugin_manager"] = pm
    registry.bridge_context["marketplaces_dir"] = tmp_path / "marketplaces"
    server = AppServer(registry)
    register_plugin_app_handlers(server)
    response = await server.dispatch(
        "1", "plugin/read",
        {"pluginName": "../secret", "marketplaceName": "local"},
        "client-1", None,
    )
    assert response["code"] == "NOT_FOUND"
    assert "../secret" not in response["error"]
