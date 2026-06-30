"""Typed result payloads for core App Server capability methods."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _CoreResult(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class EmptyResult(_CoreResult):
    pass


class ServerInfoResult(_CoreResult):
    name: str
    title: str
    version: str


class InitializeCapabilitiesResult(_CoreResult):
    experimental_api: bool = Field(validation_alias="experimentalApi")
    supports_notification_opt_out: bool = Field(validation_alias="supportsNotificationOptOut")
    supports_workbench_processes: bool = Field(validation_alias="supportsWorkbenchProcesses")
    supports_pty: bool = Field(validation_alias="supportsPty")


class InitializeResult(_CoreResult):
    server_info: ServerInfoResult = Field(validation_alias="serverInfo")
    user_agent: str = Field(validation_alias="userAgent")
    miqi_home: str = Field(validation_alias="miqiHome")
    codex_home: str = Field(validation_alias="codexHome")
    platform_family: str = Field(validation_alias="platformFamily")
    platform_os: str = Field(validation_alias="platformOs")
    client_id: str = Field(validation_alias="clientId")
    capabilities: InitializeCapabilitiesResult


class StatusResult(_CoreResult):
    status: str
    configured: bool
    python_version: str


class PythonCheckResult(_CoreResult):
    ok: bool
    python_version: str
    issues: list[str]
    config_exists: bool


class DynamicObjectResult(_CoreResult):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ConfigBatchWriteResult(_CoreResult):
    saved: bool
    applied: int
    propagated_sessions: int = Field(validation_alias="propagatedSessions")


class ConfigUpdateResult(_CoreResult):
    saved: bool
    propagated_sessions: int


class ModelListResult(_CoreResult):
    models: list[dict[str, Any]]


class ModelProviderCapabilitiesReadResult(_CoreResult):
    capabilities: dict[str, Any]


class PaginatedDataResult(_CoreResult):
    data: list[dict[str, Any]]
    next_cursor: str | None = Field(default=None, validation_alias="nextCursor")


class ExperimentalFeatureEnablementSetResult(_CoreResult):
    saved: bool
    ignored: list[str]


CORE_METHOD_RESULT_MODELS: dict[str, type[BaseModel]] = {
    "initialize": InitializeResult,
    "initialized": EmptyResult,
    "status": StatusResult,
    "python.check": PythonCheckResult,
    "config/read": DynamicObjectResult,
    "config/batchWrite": ConfigBatchWriteResult,
    "config.get": DynamicObjectResult,
    "config.update": ConfigUpdateResult,
    "model/list": ModelListResult,
    "modelProvider/capabilities/read": ModelProviderCapabilitiesReadResult,
    "experimentalFeature/list": PaginatedDataResult,
    "experimentalFeature/enablement/set": ExperimentalFeatureEnablementSetResult,
    "permissionProfile/list": PaginatedDataResult,
}
