"""Runtime-owned plugin catalog and marketplace projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.runtime.plugin_protocol import (
    InstalledPluginView,
    MarketplaceView,
    PluginDetailView,
    PluginSummaryView,
)


class PluginCatalogRuntime:
    def __init__(self, *, plugin_manager: Any, marketplaces_dir: Path) -> None:
        self.plugin_manager = plugin_manager
        self.marketplaces_dir = Path(marketplaces_dir)
        self._marketplaces: dict[str, MarketplaceView] = {
            "local": MarketplaceView(
                name="local",
                display_name="Local Plugins",
                source=str(getattr(plugin_manager, "user_dir", "")),
                path=None,
                load_errors=[],
            )
        }

    def list_marketplaces(self) -> list[MarketplaceView]:
        return list(self._marketplaces.values())

    def list_plugins(self) -> list[PluginSummaryView]:
        result: list[PluginSummaryView] = []
        for plugin in self.plugin_manager.list_plugins():
            result.append(self._summary_for_plugin(plugin, "local", None))
        return result

    def list_installed(self) -> list[InstalledPluginView]:
        rows: list[InstalledPluginView] = []
        for plugin in self.plugin_manager.list_plugins():
            name = plugin.manifest.name
            rows.append(InstalledPluginView(
                plugin_id=f"{name}@local",
                name=name,
                marketplace_name="local",
                mention=f"plugin://{name}@local",
                enabled=plugin.status == "active",
                path=str(plugin.path),
            ))
        return rows

    def read_plugin(self, *, plugin_name: str, marketplace_name: str) -> PluginDetailView:
        if marketplace_name != "local":
            raise KeyError(plugin_name)
        plugin = self.plugin_manager.get_plugin(plugin_name)
        if plugin is None:
            raise KeyError(plugin_name)
        manifest = plugin.manifest
        skills = [{"name": name, "enabled": plugin.status == "active"} for name in manifest.skills]
        hooks = self._read_hooks(plugin.path)
        return PluginDetailView(
            plugin_id=f"{manifest.name}@local",
            name=manifest.name,
            marketplace_name="local",
            marketplace_path=None,
            summary=[manifest.description] if manifest.description else [],
            description=manifest.description,
            version=manifest.version,
            skills=skills,
            hooks=hooks,
            apps=[],
            mcp_servers=list(manifest.mcp_servers),
            path=str(plugin.path),
        )

    def read_plugin_skill(
        self, *, plugin_name: str, marketplace_name: str, skill_name: str
    ) -> str:
        if marketplace_name != "local":
            raise KeyError(skill_name)
        plugin = self.plugin_manager.get_plugin(plugin_name)
        if plugin is None:
            raise KeyError(plugin_name)
        skill_path = (plugin.path / "skills" / skill_name / "SKILL.md").resolve()
        skills_root = (plugin.path / "skills").resolve()
        try:
            skill_path.relative_to(skills_root)
        except ValueError:
            raise ValueError("Invalid skill path") from None
        if not skill_path.exists():
            raise KeyError(skill_name)
        return skill_path.read_text(encoding="utf-8")

    def _summary_for_plugin(
        self, plugin: Any, marketplace_name: str, marketplace_path: str | None
    ) -> PluginSummaryView:
        manifest = plugin.manifest
        return PluginSummaryView(
            plugin_id=f"{manifest.name}@{marketplace_name}",
            name=manifest.name,
            marketplace_name=marketplace_name,
            marketplace_path=marketplace_path,
            version=manifest.version,
            description=manifest.description,
            installed=True,
            enabled=plugin.status == "active",
            availability="AVAILABLE",
            category=None,
            mcp_servers=[srv.get("name", "") for srv in manifest.mcp_servers],
            skills=list(manifest.skills),
            hooks=[hook["name"] for hook in self._read_hooks(plugin.path)],
        )

    def _read_hooks(self, plugin_path: Path) -> list[dict[str, Any]]:
        import json

        hooks_path = plugin_path / "hooks.json"
        if not hooks_path.exists():
            return []
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("hooks"), list):
            return [item for item in data["hooks"] if isinstance(item, dict)]
        return []
