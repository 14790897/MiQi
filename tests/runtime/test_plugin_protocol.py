from pathlib import Path

from miqi.runtime.plugin_protocol import (
    InstalledPluginView,
    MarketplaceView,
    PluginDetailView,
    PluginSummaryView,
)


def test_marketplace_view_serializes_codex_style():
    view = MarketplaceView(
        name="debug",
        display_name="Debug Marketplace",
        source="file:///tmp/debug",
        path=Path("/tmp/debug/.agents/plugins/marketplace.json"),
        load_errors=[],
    )
    data = view.to_dict()
    assert data["name"] == "debug"
    assert data["displayName"] == "Debug Marketplace"
    assert data["marketplacePath"].endswith("marketplace.json")
    assert data["marketplaceLoadErrors"] == []


def test_plugin_summary_view_includes_availability_and_install_state():
    view = PluginSummaryView(
        plugin_id="sample@debug",
        name="sample",
        marketplace_name="debug",
        marketplace_path="/tmp/debug/.agents/plugins/marketplace.json",
        version="1.0.0",
        description="Sample plugin",
        installed=True,
        enabled=True,
        availability="AVAILABLE",
        category="tools",
        mcp_servers=["sample-mcp"],
        skills=["sample-skill"],
        hooks=["pre-tool"],
    )
    data = view.to_dict()
    assert data["pluginId"] == "sample@debug"
    assert data["marketplaceName"] == "debug"
    assert data["installed"] is True
    assert data["enabled"] is True
    assert data["availability"] == "AVAILABLE"


def test_installed_plugin_view_is_mention_ready():
    view = InstalledPluginView(
        plugin_id="sample@local",
        name="sample",
        marketplace_name="local",
        mention="plugin://sample@local",
        enabled=True,
        path="/plugins/sample",
    )
    assert view.to_dict()["mention"] == "plugin://sample@local"


def test_plugin_detail_view_lists_bundled_assets():
    detail = PluginDetailView(
        plugin_id="sample@local",
        name="sample",
        marketplace_name="local",
        marketplace_path="/marketplace.json",
        summary=["Sample plugin", "Adds tools"],
        description="Long description",
        version="1.0.0",
        skills=[{"name": "sample-skill", "enabled": True}],
        hooks=[{"name": "pre-tool", "event": "pre_tool"}],
        apps=[],
        mcp_servers=[{"name": "sample-mcp"}],
        path="/plugins/sample",
    )
    data = detail.to_dict()
    assert data["summary"] == ["Sample plugin", "Adds tools"]
    assert data["skills"][0]["name"] == "sample-skill"
    assert data["mcpServers"][0]["name"] == "sample-mcp"
