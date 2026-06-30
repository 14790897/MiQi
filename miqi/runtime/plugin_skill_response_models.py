"""Typed result payloads for plugin, marketplace, skills, and hooks methods."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Result(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class PluginListResult(_Result):
    """plugin/list — full marketplace and plugin catalog."""

    marketplaces: list[dict[str, Any]]
    plugins: list[dict[str, Any]]
    featured_plugin_ids: list[str] = Field(default_factory=list, validation_alias="featuredPluginIds")
    marketplace_load_errors: list[dict[str, Any]] = Field(
        default_factory=list,
        validation_alias="marketplaceLoadErrors",
    )


class PluginInstalledResult(_Result):
    """plugin/installed — list of locally installed plugins."""

    plugins: list[dict[str, Any]]


class PluginReadResult(_Result):
    """plugin/read — single plugin detail."""

    plugin: dict[str, Any]


class PluginSkillReadResult(_Result):
    """plugin/skill/read — skill markdown content."""

    content: str


class PluginInstallResult(_Result):
    """plugin/install — newly installed plugin reference."""

    plugin: dict[str, Any]


class PluginUninstallResult(_Result):
    """plugin/uninstall — result of uninstall operation."""

    removed: bool
    plugin_id: str = Field(validation_alias="pluginId")


class MarketplaceAddResult(_Result):
    """marketplace/add — registered marketplace view."""

    marketplace: dict[str, Any]
    already_present: bool = Field(validation_alias="alreadyPresent")


class MarketplaceRemoveResult(_Result):
    """marketplace/remove — result of marketplace removal."""

    removed: bool
    marketplace_name: str = Field(validation_alias="marketplaceName")


class MarketplaceUpgradeResult(_Result):
    """marketplace/upgrade — selected marketplaces for refresh."""

    selected_marketplaces: list[str] = Field(validation_alias="selectedMarketplaces")
    errors: list[dict[str, Any]] = Field(default_factory=list)


class SkillsListResult(_Result):
    """skills/list — skills found in workspace(s)."""

    skills: list[dict[str, Any]]


class SkillsExtraRootsSetResult(_Result):
    """skills/extraRoots/set — empty result on success."""

    pass


class HooksListResult(_Result):
    """hooks/list — hooks found in workspace(s)."""

    hooks: list[dict[str, Any]]


PLUGIN_SKILL_METHOD_RESULT_MODELS: dict[str, type[BaseModel]] = {
    "plugin/list": PluginListResult,
    "plugin/installed": PluginInstalledResult,
    "plugin/read": PluginReadResult,
    "plugin/skill/read": PluginSkillReadResult,
    "plugin/install": PluginInstallResult,
    "plugin/uninstall": PluginUninstallResult,
    "marketplace/add": MarketplaceAddResult,
    "marketplace/remove": MarketplaceRemoveResult,
    "marketplace/upgrade": MarketplaceUpgradeResult,
    "skills/list": SkillsListResult,
    "skills/extraRoots/set": SkillsExtraRootsSetResult,
    "hooks/list": HooksListResult,
}
