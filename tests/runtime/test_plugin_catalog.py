import json
from pathlib import Path

import pytest

from miqi.runtime.plugin_catalog import PluginCatalogRuntime
from miqi.skills.plugin_manager import PluginManager


def write_plugin(root: Path, name: str, *, skill: bool = True) -> Path:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({
        "name": name,
        "version": "1.0.0",
        "description": f"{name} plugin",
        "author": "test",
        "mcp_servers": [{"name": f"{name}-mcp", "command": "echo", "args": ["ok"]}],
        "skills": [f"{name}-skill"] if skill else [],
        "slash_commands": [],
    }), encoding="utf-8")
    if skill:
        skill_dir = plugin_dir / "skills" / f"{name}-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: {0}-skill\ndescription: Skill from {0}\n---\n\n# Skill\n".format(name),
            encoding="utf-8",
        )
    return plugin_dir


@pytest.mark.asyncio
async def test_catalog_lists_installed_plugins(tmp_path):
    user_dir = tmp_path / "user"
    system_dir = tmp_path / "system"
    write_plugin(user_dir, "sample")
    pm = PluginManager(user_dir, system_dir)
    await pm.discover()
    catalog = PluginCatalogRuntime(plugin_manager=pm, marketplaces_dir=tmp_path / "marketplaces")

    installed = catalog.list_installed()
    assert installed[0].plugin_id == "sample@local"
    assert installed[0].mention == "plugin://sample@local"


@pytest.mark.asyncio
async def test_catalog_reads_plugin_detail(tmp_path):
    user_dir = tmp_path / "user"
    system_dir = tmp_path / "system"
    write_plugin(user_dir, "sample")
    pm = PluginManager(user_dir, system_dir)
    await pm.discover()
    catalog = PluginCatalogRuntime(plugin_manager=pm, marketplaces_dir=tmp_path / "marketplaces")

    detail = catalog.read_plugin(plugin_name="sample", marketplace_name="local")
    data = detail.to_dict()
    assert data["pluginId"] == "sample@local"
    assert data["skills"][0]["name"] == "sample-skill"
    assert data["mcpServers"][0]["name"] == "sample-mcp"


@pytest.mark.asyncio
async def test_catalog_reads_plugin_skill_markdown(tmp_path):
    user_dir = tmp_path / "user"
    system_dir = tmp_path / "system"
    write_plugin(user_dir, "sample")
    pm = PluginManager(user_dir, system_dir)
    await pm.discover()
    catalog = PluginCatalogRuntime(plugin_manager=pm, marketplaces_dir=tmp_path / "marketplaces")

    content = catalog.read_plugin_skill(
        plugin_name="sample",
        marketplace_name="local",
        skill_name="sample-skill",
    )
    assert "# Skill" in content
