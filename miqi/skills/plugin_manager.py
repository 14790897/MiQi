"""Plugin discovery and lifecycle management.

Plugins are the top-level packaging format. A plugin can contain:
- Multiple MCP servers (tools)
- Multiple skills (instruction sets)
- Slash commands
- Additional configuration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class PluginManifest:
    """Manifest file found in a plugin directory (plugin.json)."""
    name: str
    version: str
    description: str
    author: str = ""
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    slash_commands: list[dict[str, str]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class LoadedPlugin:
    """A successfully loaded and active plugin."""
    manifest: PluginManifest
    path: Path
    scope: str  # "user" | "workspace" | "system"
    status: str = "active"  # "active" | "error" | "disabled"
    error: str | None = None


class PluginManager:
    """Discovers, loads, and manages plugins.

    Plugin search paths (in order):
    1. ~/.miqi/plugins/           — user plugins
    2. <workspace>/.miqi/plugins/ — workspace plugins
    3. <miqi_install>/plugins/    — system/builtin plugins
    """

    def __init__(
        self,
        user_plugins_dir: Path,
        system_plugins_dir: Path,
        workspace: Path | None = None,
    ):
        self.user_dir = Path(user_plugins_dir)
        self.system_dir = Path(system_plugins_dir)
        self.workspace = workspace
        self._plugins: dict[str, LoadedPlugin] = {}

    async def discover(self) -> list[LoadedPlugin]:
        """Discover all plugins across all search paths."""
        search_paths = [
            (self.user_dir, "user"),
            (self.system_dir, "system"),
        ]
        if self.workspace:
            search_paths.append(
                (self.workspace / ".miqi" / "plugins", "workspace")
            )

        discovered = []
        for base_dir, scope in search_paths:
            if not base_dir.exists():
                continue
            for plugin_dir in base_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                manifest_path = plugin_dir / "plugin.json"
                if not manifest_path.exists():
                    continue
                try:
                    plugin = await self._load_plugin(
                        plugin_dir, manifest_path, scope
                    )
                    if plugin:
                        self._plugins[plugin.manifest.name] = plugin
                        discovered.append(plugin)
                except Exception as e:
                    logger.error(
                        "Failed to load plugin {}: {}",
                        plugin_dir.name, e,
                    )

        logger.info("Discovered {} plugins", len(discovered))
        return discovered

    async def _load_plugin(
        self,
        plugin_dir: Path,
        manifest_path: Path,
        scope: str,
    ) -> LoadedPlugin | None:
        """Load a single plugin from its directory."""
        import json
        manifest_data = json.loads(manifest_path.read_text())
        manifest = PluginManifest(**manifest_data)
        return LoadedPlugin(
            manifest=manifest, path=plugin_dir, scope=scope
        )

    def get_mcp_servers(self) -> list[dict[str, Any]]:
        """Collect all MCP server configs from active plugins."""
        servers = []
        for plugin in self._plugins.values():
            if plugin.status != "active":
                continue
            for server in plugin.manifest.mcp_servers:
                resolved = dict(server)
                if "cwd" not in resolved:
                    resolved["cwd"] = str(plugin.path)
                servers.append(resolved)
        return servers

    def get_slash_commands(self) -> dict[str, str]:
        """Collect all slash commands from active plugins."""
        commands = {}
        for plugin in self._plugins.values():
            if plugin.status != "active":
                continue
            for cmd in plugin.manifest.slash_commands:
                commands[cmd["name"]] = cmd["description"]
        return commands

    def list_plugins(self) -> list[LoadedPlugin]:
        """List all loaded plugins."""
        return list(self._plugins.values())
