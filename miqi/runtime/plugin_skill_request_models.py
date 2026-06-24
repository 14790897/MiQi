"""Typed request params for plugin, marketplace, skills, and hooks methods."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from miqi.runtime.app_server import AppServerError


class _Params(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class PluginReadParams(_Params):
    """plugin/read — resolve a single plugin's metadata.

    Accepts pluginName, plugin_name, or name.
    """

    plugin_name: str = Field(default="", validation_alias="pluginName")
    name: str | None = None
    marketplace_name: str | None = Field(default=None, validation_alias="marketplaceName")

    @model_validator(mode="after")
    def _merge(self) -> "PluginReadParams":
        if not self.plugin_name and self.name:
            self.plugin_name = self.name
        if not self.plugin_name.strip():
            raise ValueError("pluginName is required")
        return self

    @field_validator("plugin_name", "name", mode="before")
    @classmethod
    def _check_plugin_name(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("plugin name must be a non-empty string")
        return value.strip() if isinstance(value, str) else value

    @field_validator("marketplace_name", mode="before")
    @classmethod
    def _check_marketplace_name(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("marketplace name must be a non-empty string")
        return value.strip() if isinstance(value, str) else value


class PluginSkillReadParams(_Params):
    """plugin/skill/read — read a skill definition from a plugin."""

    plugin_name: str = Field(default="", validation_alias="pluginName")
    skill_name: str = Field(default="", validation_alias="skillName")
    marketplace_name: str | None = Field(default=None, validation_alias="marketplaceName")

    @model_validator(mode="after")
    def _check_required(self) -> "PluginSkillReadParams":
        if not self.plugin_name.strip():
            raise ValueError("pluginName is required")
        if not self.skill_name.strip():
            raise ValueError("skillName is required")
        return self

    @field_validator("plugin_name", "skill_name", mode="before")
    @classmethod
    def _required_string(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()

    @field_validator("marketplace_name", mode="before")
    @classmethod
    def _optional_string(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("marketplace name must be a non-empty string")
        return value.strip() if isinstance(value, str) else value


class PluginInstallParams(_Params):
    """plugin/install — install a plugin from source."""

    plugin_name: str = Field(default="", validation_alias="pluginName")
    plugin_id: str | None = Field(default=None, validation_alias="pluginId")
    name: str | None = None
    source: str = ""
    url: str | None = None

    @model_validator(mode="after")
    def _merge(self) -> "PluginInstallParams":
        if not self.plugin_name and self.plugin_id:
            self.plugin_name = self.plugin_id
        if not self.plugin_name and self.name:
            self.plugin_name = self.name
        if not self.plugin_name.strip():
            raise ValueError("pluginName is required")
        if not self.source and self.url:
            self.source = self.url
        if not self.source.strip():
            raise ValueError("source is required")
        return self

    @field_validator("plugin_name", "plugin_id", "name", mode="before")
    @classmethod
    def _check_name_fields(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("plugin name fields must be non-empty strings")
        return value.strip() if isinstance(value, str) else value

    @field_validator("source", "url", mode="before")
    @classmethod
    def _check_source_fields(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("source/url must be non-empty strings")
        return value.strip() if isinstance(value, str) else value


class PluginUninstallParams(_Params):
    """plugin/uninstall — remove an installed plugin."""

    plugin_id: str = Field(default="", validation_alias="pluginId")
    plugin_name: str | None = Field(default=None, validation_alias="pluginName")
    name: str | None = None

    @model_validator(mode="after")
    def _merge(self) -> "PluginUninstallParams":
        if not self.plugin_id and self.plugin_name:
            self.plugin_id = self.plugin_name
        if not self.plugin_id and self.name:
            self.plugin_id = self.name
        if not self.plugin_id.strip():
            raise ValueError("pluginId is required")
        return self

    @field_validator("plugin_id", "plugin_name", "name", mode="before")
    @classmethod
    def _check_name_fields(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("plugin id fields must be non-empty strings")
        return value.strip() if isinstance(value, str) else value


class MarketplaceAddParams(_Params):
    """marketplace/add — register a marketplace source."""

    name: str = Field(default="")
    marketplace_name: str | None = Field(default=None, validation_alias="marketplaceName")
    source: str = ""

    @model_validator(mode="after")
    def _merge(self) -> "MarketplaceAddParams":
        if not self.name and self.marketplace_name:
            self.name = self.marketplace_name
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.source.strip():
            raise ValueError("source is required")
        return self

    @field_validator("name", "marketplace_name", mode="before")
    @classmethod
    def _check_name(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("marketplace name must be a non-empty string")
        return value.strip() if isinstance(value, str) else value

    @field_validator("source", mode="before")
    @classmethod
    def _check_source(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("source must be a non-empty string")
        return value.strip()


class MarketplaceRemoveParams(_Params):
    """marketplace/remove — unregister a marketplace."""

    name: str = Field(default="")
    marketplace_name: str | None = Field(default=None, validation_alias="marketplaceName")

    @model_validator(mode="after")
    def _merge(self) -> "MarketplaceRemoveParams":
        if not self.name and self.marketplace_name:
            self.name = self.marketplace_name
        if not self.name.strip():
            raise ValueError("name is required")
        return self

    @field_validator("name", "marketplace_name", mode="before")
    @classmethod
    def _check_name(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("marketplace name must be a non-empty string")
        return value.strip() if isinstance(value, str) else value


class MarketplaceUpgradeParams(_Params):
    """marketplace/upgrade — refresh marketplace listings or a single one."""

    marketplace_name: str | None = Field(default=None, validation_alias="marketplaceName")

    @field_validator("marketplace_name", mode="before")
    @classmethod
    def _check_name(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("marketplaceName must be a non-empty string")
        return value.strip() if isinstance(value, str) else value


class SkillsListParams(_Params):
    """skills/list — list skills across one or more working directories."""

    cwds: list[str] = Field(default_factory=list)
    cwd: str | None = None

    @model_validator(mode="after")
    def _merge(self) -> "SkillsListParams":
        if self.cwd is not None:
            if not self.cwds:
                self.cwds = [self.cwd]
        return self

    @field_validator("cwds", mode="before")
    @classmethod
    def _check_cwds(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("cwds must be a list")
        for item in value:
            if not isinstance(item, str):
                raise ValueError("cwds items must be strings")
        return value

    @field_validator("cwd", mode="before")
    @classmethod
    def _check_cwd(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, str):
            raise ValueError("cwd must be a string")
        return value


class SkillsExtraRootsSetParams(_Params):
    """skills/extraRoots/set — update extra skills roots."""

    roots: list[str]

    @field_validator("roots", mode="before")
    @classmethod
    def _check_roots(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("roots must be a list")
        for item in value:
            if not isinstance(item, str):
                raise ValueError("roots items must be strings")
        return value


class HooksListParams(_Params):
    """hooks/list — list hooks in working directories."""

    cwds: list[str] = Field(default_factory=list)

    @field_validator("cwds", mode="before")
    @classmethod
    def _check_cwds(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("cwds must be a list")
        for item in value:
            if not isinstance(item, str):
                raise ValueError("cwds items must be strings")
        return value


PLUGIN_SKILL_METHOD_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "plugin/list": type("PluginListParams", (_Params,), {}),
    "plugin/installed": type("PluginInstalledParams", (_Params,), {}),
    "plugin/read": PluginReadParams,
    "plugin/skill/read": PluginSkillReadParams,
    "plugin/install": PluginInstallParams,
    "plugin/uninstall": PluginUninstallParams,
    "marketplace/add": MarketplaceAddParams,
    "marketplace/remove": MarketplaceRemoveParams,
    "marketplace/upgrade": MarketplaceUpgradeParams,
    "skills/list": SkillsListParams,
    "skills/extraRoots/set": SkillsExtraRootsSetParams,
    "hooks/list": HooksListParams,
}


def validate_plugin_skill_params(method: str, params: dict[str, Any]) -> BaseModel:
    model = PLUGIN_SKILL_METHOD_PARAM_MODELS[method]
    try:
        return model.model_validate(params)
    except ValidationError as exc:
        raise AppServerError("Invalid params", code="INVALID_PARAMS") from exc
