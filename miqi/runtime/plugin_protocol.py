"""Codex-style plugin, marketplace, and skill protocol projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_str(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path)


@dataclass(frozen=True)
class MarketplaceView:
    name: str
    display_name: str
    source: str
    path: Path | str | None
    load_errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "displayName": self.display_name,
            "source": self.source,
            "marketplacePath": _path_str(self.path),
            "marketplaceLoadErrors": list(self.load_errors),
        }


@dataclass(frozen=True)
class PluginSummaryView:
    plugin_id: str
    name: str
    marketplace_name: str
    marketplace_path: str | None
    version: str
    description: str
    installed: bool
    enabled: bool
    availability: str
    category: str | None = None
    mcp_servers: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pluginId": self.plugin_id,
            "name": self.name,
            "marketplaceName": self.marketplace_name,
            "marketplacePath": self.marketplace_path,
            "version": self.version,
            "description": self.description,
            "installed": self.installed,
            "enabled": self.enabled,
            "availability": self.availability,
            "interface": {"category": self.category},
            "mcpServers": list(self.mcp_servers),
            "skills": list(self.skills),
            "hooks": list(self.hooks),
        }


@dataclass(frozen=True)
class InstalledPluginView:
    plugin_id: str
    name: str
    marketplace_name: str
    mention: str
    enabled: bool
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pluginId": self.plugin_id,
            "name": self.name,
            "marketplaceName": self.marketplace_name,
            "mention": self.mention,
            "enabled": self.enabled,
            "path": self.path,
        }


@dataclass(frozen=True)
class PluginDetailView:
    plugin_id: str
    name: str
    marketplace_name: str
    marketplace_path: str | None
    summary: list[str]
    description: str
    version: str
    skills: list[dict[str, Any]]
    hooks: list[dict[str, Any]]
    apps: list[dict[str, Any]]
    mcp_servers: list[dict[str, Any]]
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pluginId": self.plugin_id,
            "name": self.name,
            "marketplaceName": self.marketplace_name,
            "marketplacePath": self.marketplace_path,
            "summary": list(self.summary),
            "description": self.description,
            "version": self.version,
            "skills": list(self.skills),
            "hooks": list(self.hooks),
            "apps": list(self.apps),
            "mcpServers": list(self.mcp_servers),
            "path": self.path,
        }
