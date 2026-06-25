"""Export typed App Server protocol contracts to TypeScript."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import miqi.runtime.protocol_specs as specs
from miqi.runtime.core_request_models import CORE_METHOD_PARAM_MODELS
from miqi.runtime.core_response_models import CORE_METHOD_RESULT_MODELS
from miqi.runtime.filesystem_request_models import FILESYSTEM_METHOD_PARAM_MODELS
from miqi.runtime.plugin_skill_request_models import PLUGIN_SKILL_METHOD_PARAM_MODELS
from miqi.runtime.plugin_skill_response_models import PLUGIN_SKILL_METHOD_RESULT_MODELS
from miqi.runtime.process_request_models import COMMAND_PROCESS_METHOD_PARAM_MODELS
from miqi.runtime.filesystem_response_models import (
    FILESYSTEM_EVENT_MODELS,
    FILESYSTEM_METHOD_RESULT_MODELS,
)
from miqi.runtime.process_response_models import (
    PROCESS_EVENT_MODELS,
    PROCESS_METHOD_RESULT_MODELS,
)
from miqi.runtime.protocol_model_schema import params_schema_from_model, result_schema_from_model
from miqi.runtime.turn_request_models import TURN_METHOD_PARAM_MODELS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "apps" / "desktop" / "src" / "shared" / "app-protocol.ts"


MODEL_MAP = {
    **CORE_METHOD_PARAM_MODELS,
    **PLUGIN_SKILL_METHOD_PARAM_MODELS,
    **TURN_METHOD_PARAM_MODELS,
    **COMMAND_PROCESS_METHOD_PARAM_MODELS,
    **FILESYSTEM_METHOD_PARAM_MODELS,
}

RESULT_MODEL_MAP = {
    **CORE_METHOD_RESULT_MODELS,
    **PLUGIN_SKILL_METHOD_RESULT_MODELS,
    **PROCESS_METHOD_RESULT_MODELS,
    **FILESYSTEM_METHOD_RESULT_MODELS,
}

EVENT_MODEL_MAP = {
    **PROCESS_EVENT_MODELS,
    **FILESYSTEM_EVENT_MODELS,
}


METHOD_TO_SPEC = {
    "initialize": specs.INITIALIZE,
    "initialized": specs.INITIALIZED,
    "status": specs.STATUS,
    "python.check": specs.PYTHON_CHECK,
    "config/read": specs.CONFIG_READ,
    "config/batchWrite": specs.CONFIG_BATCH_WRITE,
    "config.get": specs.CONFIG_GET,
    "config.update": specs.CONFIG_UPDATE,
    "model/list": specs.MODEL_LIST,
    "modelProvider/capabilities/read": specs.MODEL_PROVIDER_CAPABILITIES_READ,
    "experimentalFeature/list": specs.EXPERIMENTAL_FEATURE_LIST,
    "experimentalFeature/enablement/set": specs.EXPERIMENTAL_FEATURE_ENABLEMENT_SET,
    "permissionProfile/list": specs.PERMISSION_PROFILE_LIST,
    "plugin/list": specs.PLUGIN_LIST,
    "plugin/installed": specs.PLUGIN_INSTALLED,
    "plugin/read": specs.PLUGIN_READ,
    "plugin/skill/read": specs.PLUGIN_SKILL_READ,
    "plugin/install": specs.PLUGIN_INSTALL,
    "plugin/uninstall": specs.PLUGIN_UNINSTALL,
    "marketplace/add": specs.MARKETPLACE_ADD,
    "marketplace/remove": specs.MARKETPLACE_REMOVE,
    "marketplace/upgrade": specs.MARKETPLACE_UPGRADE,
    "skills/list": specs.SKILLS_LIST,
    "skills/extraRoots/set": specs.SKILLS_EXTRA_ROOTS_SET,
    "hooks/list": specs.HOOKS_LIST,
    "turn/start": specs.TURN_START,
    "turn/interrupt": specs.TURN_INTERRUPT,
    "turn/steer": specs.TURN_STEER,
    "thread/compact/start": specs.THREAD_COMPACT_START,
    "thread/inject_items": specs.THREAD_INJECT_ITEMS,
    "command/exec": specs.COMMAND_EXEC,
    "command/exec/write": specs.COMMAND_EXEC_WRITE,
    "command/exec/resize": specs.COMMAND_EXEC_RESIZE,
    "command/exec/terminate": specs.COMMAND_EXEC_TERMINATE,
    "process/spawn": specs.PROCESS_SPAWN,
    "process/writeStdin": specs.PROCESS_WRITE_STDIN,
    "process/resizePty": specs.PROCESS_RESIZE_PTY,
    "process/kill": specs.PROCESS_KILL,
    "fs/readFile": specs.FS_READ_FILE,
    "fs/writeFile": specs.FS_WRITE_FILE,
    "fs/createDirectory": specs.FS_CREATE_DIRECTORY,
    "fs/getMetadata": specs.FS_GET_METADATA,
    "fs/readDirectory": specs.FS_READ_DIRECTORY,
    "fs/remove": specs.FS_REMOVE,
    "fs/copy": specs.FS_COPY,
    "fs/watch": specs.FS_WATCH,
    "fs/unwatch": specs.FS_UNWATCH,
    "fuzzyFileSearch": specs.FUZZY_FILE_SEARCH,
    "fuzzyFileSearch/sessionStart": specs.FUZZY_FILE_SEARCH_SESSION_START,
    "fuzzyFileSearch/sessionUpdate": specs.FUZZY_FILE_SEARCH_SESSION_UPDATE,
    "fuzzyFileSearch/sessionStop": specs.FUZZY_FILE_SEARCH_SESSION_STOP,
}


TYPE_NAME_BY_METHOD = {
    "initialize": "InitializeParams",
    "initialized": "InitializedParams",
    "status": "StatusParams",
    "python.check": "PythonCheckParams",
    "config/read": "ConfigReadParams",
    "config/batchWrite": "ConfigBatchWriteParams",
    "config.get": "ConfigGetParams",
    "config.update": "ConfigUpdateParams",
    "model/list": "ModelListParams",
    "modelProvider/capabilities/read": "ModelProviderCapabilitiesReadParams",
    "experimentalFeature/list": "ExperimentalFeatureListParams",
    "experimentalFeature/enablement/set": "ExperimentalFeatureEnablementSetParams",
    "permissionProfile/list": "PermissionProfileListParams",
    "plugin/list": "PluginListParams",
    "plugin/installed": "PluginInstalledParams",
    "plugin/read": "PluginReadParams",
    "plugin/skill/read": "PluginSkillReadParams",
    "plugin/install": "PluginInstallParams",
    "plugin/uninstall": "PluginUninstallParams",
    "marketplace/add": "MarketplaceAddParams",
    "marketplace/remove": "MarketplaceRemoveParams",
    "marketplace/upgrade": "MarketplaceUpgradeParams",
    "skills/list": "SkillsListParams",
    "skills/extraRoots/set": "SkillsExtraRootsSetParams",
    "hooks/list": "HooksListParams",
    "turn/start": "TurnStartParams",
    "turn/interrupt": "TurnInterruptParams",
    "turn/steer": "TurnSteerParams",
    "thread/compact/start": "ThreadCompactStartParams",
    "thread/inject_items": "ThreadInjectItemsParams",
    "command/exec": "CommandExecParams",
    "command/exec/write": "CommandExecWriteParams",
    "command/exec/resize": "CommandExecResizeParams",
    "command/exec/terminate": "CommandExecTerminateParams",
    "process/spawn": "ProcessSpawnParams",
    "process/writeStdin": "ProcessWriteStdinParams",
    "process/resizePty": "ProcessResizePtyParams",
    "process/kill": "ProcessKillParams",
    "fs/readFile": "FsReadFileParams",
    "fs/writeFile": "FsWriteFileParams",
    "fs/createDirectory": "FsCreateDirectoryParams",
    "fs/getMetadata": "FsGetMetadataParams",
    "fs/readDirectory": "FsReadDirectoryParams",
    "fs/remove": "FsRemoveParams",
    "fs/copy": "FsCopyParams",
    "fs/watch": "FsWatchParams",
    "fs/unwatch": "FsUnwatchParams",
    "fuzzyFileSearch": "FuzzyFileSearchParams",
    "fuzzyFileSearch/sessionStart": "FuzzySessionStartParams",
    "fuzzyFileSearch/sessionUpdate": "FuzzySessionUpdateParams",
    "fuzzyFileSearch/sessionStop": "FuzzySessionStopParams",
}


RESULT_TYPE_NAME_BY_METHOD = {
    "initialize": "InitializeResult",
    "initialized": "InitializedResult",
    "status": "StatusResult",
    "python.check": "PythonCheckResult",
    "config/read": "ConfigReadResult",
    "config/batchWrite": "ConfigBatchWriteResult",
    "config.get": "ConfigGetResult",
    "config.update": "ConfigUpdateResult",
    "model/list": "ModelListResult",
    "modelProvider/capabilities/read": "ModelProviderCapabilitiesReadResult",
    "experimentalFeature/list": "ExperimentalFeatureListResult",
    "experimentalFeature/enablement/set": "ExperimentalFeatureEnablementSetResult",
    "permissionProfile/list": "PermissionProfileListResult",
    **{
        method: TYPE_NAME_BY_METHOD[method].replace("Params", "Result")
        for method in RESULT_MODEL_MAP
        if method not in {
            "initialize",
            "initialized",
            "status",
            "python.check",
            "config/read",
            "config/batchWrite",
            "config.get",
            "config.update",
            "model/list",
            "modelProvider/capabilities/read",
            "experimentalFeature/list",
            "experimentalFeature/enablement/set",
            "permissionProfile/list",
        }
    },
}

EVENT_TYPE_NAME_BY_EVENT = {
    "command/exec/outputDelta": "CommandExecOutputDeltaEventPayload",
    "process/outputDelta": "ProcessOutputDeltaEventPayload",
    "process/exited": "ProcessExitedEventPayload",
    "fs/changed": "FsChangedEventPayload",
    "fuzzyFileSearch/sessionUpdated": "FuzzySessionUpdatedEventPayload",
    "fuzzyFileSearch/sessionCompleted": "FuzzySessionCompletedEventPayload",
}


def _ts_identifier(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name)


def _schema_to_ts(schema: dict[str, Any]) -> str:
    if "anyOf" in schema:
        return " | ".join(sorted({_schema_to_ts(part) for part in schema["anyOf"]}))
    typ = schema.get("type")
    if isinstance(typ, list):
        return " | ".join(sorted(_schema_to_ts({"type": item}) for item in typ))
    if typ == "string":
        return "string"
    if typ in {"integer", "number"}:
        return "number"
    if typ == "boolean":
        return "boolean"
    if typ == "null":
        return "null"
    if typ == "array":
        item_type = _schema_to_ts(schema.get("items") or {})
        return f"{item_type}[]"
    if typ == "object":
        props = schema.get("properties")
        if isinstance(props, dict) and props:
            required = set(schema.get("required") or [])
            fields = []
            for key in sorted(props):
                optional = "" if key in required else "?"
                fields.append(f"{key}{optional}: {_schema_to_ts(props[key])}")
            return "{ " + "; ".join(fields) + " }"
        return "Record<string, unknown>"
    return "unknown"


def _render_interface(type_name: str, schema: dict[str, Any]) -> str:
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    lines = [f"export interface {type_name} {{"]
    for key in sorted(properties):
        optional = "" if key in required else "?"
        lines.append(f"  {key}{optional}: {_schema_to_ts(properties[key])}")
    lines.append("}")
    return "\n".join(lines)


def render_typescript_contract() -> str:
    methods = sorted(MODEL_MAP)
    chunks: list[str] = [
        "/* eslint-disable */",
        "// This file is generated by miqi.runtime.export_app_protocol_ts.",
        "// Do not edit by hand; update Python request models and regenerate.",
        "",
        "export const APP_PROTOCOL_GENERATED_AT = 'static' as const",
        "",
        "export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }",
        "export type EmptyObject = Record<string, never>",
        "",
    ]

    # ---- request params interfaces ----
    for method in methods:
        model = MODEL_MAP[method]
        type_name = TYPE_NAME_BY_METHOD[method]
        schema = params_schema_from_model(model)
        chunks.append(_render_interface(type_name, schema))
        chunks.append("")

    # ---- result interfaces ----
    for method in sorted(RESULT_MODEL_MAP):
        model = RESULT_MODEL_MAP[method]
        type_name = RESULT_TYPE_NAME_BY_METHOD[method]
        schema = result_schema_from_model(model)
        chunks.append(_render_interface(type_name, schema))
        chunks.append("")

    # ---- event payload interfaces ----
    for event_name in sorted(EVENT_MODEL_MAP):
        model = EVENT_MODEL_MAP[event_name]
        type_name = EVENT_TYPE_NAME_BY_EVENT[event_name]
        schema = result_schema_from_model(model)
        chunks.append(_render_interface(type_name, schema))
        chunks.append("")

    method_literals = ",\n  ".join(f"'{method}'" for method in methods)
    chunks.append(f"export const APP_METHODS = [\n  {method_literals},\n] as const")
    chunks.append("export type AppMethod = typeof APP_METHODS[number]")
    chunks.append("")

    chunks.append("export interface AppMethodParams {")
    for method in methods:
        chunks.append(f"  '{method}': {TYPE_NAME_BY_METHOD[method]}")
    chunks.append("}")
    chunks.append("")

    chunks.append("export interface AppMethodResult {")
    for method in methods:
        result_type = RESULT_TYPE_NAME_BY_METHOD.get(method, "Record<string, unknown>")
        chunks.append(f"  '{method}': {result_type}")
    chunks.append("}")
    chunks.append("")

    chunks.append("export interface AppMethodEvents {")
    for method in methods:
        emits = METHOD_TO_SPEC[method].emits
        event_type = "never" if not emits else " | ".join(f"'{event}'" for event in sorted(emits))
        chunks.append(f"  '{method}': {event_type}")
    chunks.append("}")
    chunks.append("")

    chunks.append("export interface AppEventPayloadMap {")
    for event_name in sorted(EVENT_MODEL_MAP):
        chunks.append(f"  '{event_name}': {EVENT_TYPE_NAME_BY_EVENT[event_name]}")
    chunks.append("}")
    chunks.append("export type AppEventName = keyof AppEventPayloadMap")
    chunks.append("")

    chunks.extend([
        "export type AppEventPayload<E extends AppEventName> = AppEventPayloadMap[E]",
        "",
        "export type AppRequest<M extends AppMethod = AppMethod> = {",
        "  id: string",
        "  method: M",
        "  params: AppMethodParams[M]",
        "}",
        "",
        "export type AppResult<M extends AppMethod> = AppMethodResult[M]",
        "export type AppParams<M extends AppMethod> = AppMethodParams[M]",
        "export type AppEvent<M extends AppMethod> = AppMethodEvents[M]",
        "",
    ])

    return "\n".join(chunks).rstrip() + "\n"


def write_typescript_contract(path: Path = DEFAULT_OUTPUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_typescript_contract(), encoding="utf-8")


def main() -> None:
    write_typescript_contract()


if __name__ == "__main__":
    main()
