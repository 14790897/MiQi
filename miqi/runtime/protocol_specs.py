"""Explicit App Server protocol specs for high-value Codex-style methods."""

from __future__ import annotations

from typing import Any

from miqi.runtime.filesystem_request_models import (
    FsCopyParams,
    FsCreateDirectoryParams,
    FsGetMetadataParams,
    FsReadDirectoryParams,
    FsReadFileParams,
    FsRemoveParams,
    FsUnwatchParams,
    FsWatchParams,
    FsWriteFileParams,
    FuzzyFileSearchParams,
    FuzzySessionStartParams,
    FuzzySessionStopParams,
    FuzzySessionUpdateParams,
)
from miqi.runtime.filesystem_response_models import (
    FILESYSTEM_EVENT_MODELS,
    FILESYSTEM_METHOD_RESULT_MODELS,
)
from miqi.runtime.core_request_models import (
    CORE_METHOD_PARAM_MODELS,
    ConfigBatchWriteParams,
    ConfigUpdateParams,
    EmptyParams,
    ExperimentalFeatureEnablementSetParams,
    ExperimentalFeatureListParams,
    InitializeParams,
    ModelListParams,
    ModelProviderCapabilitiesReadParams,
    PermissionProfileListParams,
)
from miqi.runtime.core_response_models import CORE_METHOD_RESULT_MODELS
from miqi.runtime.process_request_models import (
    CommandExecParams,
    CommandExecResizeParams,
    CommandExecTerminateParams,
    CommandExecWriteParams,
    ProcessKillParams,
    ProcessResizePtyParams,
    ProcessSpawnParams,
    ProcessWriteStdinParams,
)
from miqi.runtime.process_response_models import (
    PROCESS_EVENT_MODELS,
    PROCESS_METHOD_RESULT_MODELS,
)
from miqi.runtime.protocol_model_schema import model_spec
from miqi.runtime.protocol_registry import (
    MethodScope,
    MethodStability,
    ProtocolMethodSpec,
)
from miqi.runtime.turn_request_models import (
    ThreadCompactStartParams,
    ThreadInjectItemsParams,
    TurnInterruptParams,
    TurnStartParams,
    TurnSteerParams,
)


OBJECT: dict[str, Any] = {"type": "object"}
EMPTY_RESULT: dict[str, Any] = {"type": "object", "additionalProperties": True}


def object_schema(*, required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "additionalProperties": True}
    if required:
        schema["required"] = required
    return schema


def spec(
    method: str,
    *,
    scope: MethodScope,
    stability: MethodStability = MethodStability.STABLE,
    required: list[str] | None = None,
    emits: list[str] | None = None,
    description: str | None = None,
) -> ProtocolMethodSpec:
    return ProtocolMethodSpec(
        method=method,
        stability=stability,
        scope=scope,
        params_schema=object_schema(required=required),
        result_schema=EMPTY_RESULT,
        emits=emits or [],
        description=description,
    )


INITIALIZE = model_spec(
    "initialize",
    InitializeParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["initialize"],
    description="Negotiate client identity and capabilities.",
)

INITIALIZED = model_spec(
    "initialized",
    EmptyParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["initialized"],
    description="Acknowledge initialize completion.",
)

STATUS = model_spec(
    "status",
    EmptyParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["status"],
)

PYTHON_CHECK = model_spec(
    "python.check",
    EmptyParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["python.check"],
)

CONFIG_READ = model_spec(
    "config/read",
    EmptyParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["config/read"],
)

CONFIG_BATCH_WRITE = model_spec(
    "config/batchWrite",
    ConfigBatchWriteParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["config/batchWrite"],
)

CONFIG_GET = model_spec(
    "config.get",
    EmptyParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["config.get"],
)

CONFIG_UPDATE = model_spec(
    "config.update",
    ConfigUpdateParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["config.update"],
)

MODEL_LIST = model_spec(
    "model/list",
    ModelListParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["model/list"],
)

MODEL_PROVIDER_CAPABILITIES_READ = model_spec(
    "modelProvider/capabilities/read",
    ModelProviderCapabilitiesReadParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["modelProvider/capabilities/read"],
)

EXPERIMENTAL_FEATURE_LIST = model_spec(
    "experimentalFeature/list",
    ExperimentalFeatureListParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["experimentalFeature/list"],
)

EXPERIMENTAL_FEATURE_ENABLEMENT_SET = model_spec(
    "experimentalFeature/enablement/set",
    ExperimentalFeatureEnablementSetParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["experimentalFeature/enablement/set"],
)

PERMISSION_PROFILE_LIST = model_spec(
    "permissionProfile/list",
    PermissionProfileListParams,
    scope=MethodScope.CONNECTION,
    result_model=CORE_METHOD_RESULT_MODELS["permissionProfile/list"],
)

TURN_START = model_spec(
    "turn/start",
    TurnStartParams,
    scope=MethodScope.TURN,
    emits=["turn/started", "item/started", "item/completed", "turn/completed"],
)
TURN_INTERRUPT = model_spec("turn/interrupt", TurnInterruptParams, scope=MethodScope.TURN)
TURN_STEER = model_spec("turn/steer", TurnSteerParams, scope=MethodScope.TURN)
THREAD_COMPACT_START = model_spec(
    "thread/compact/start",
    ThreadCompactStartParams,
    scope=MethodScope.THREAD,
    emits=["turn/started", "item/started", "item/completed", "turn/completed"],
)
THREAD_INJECT_ITEMS = model_spec("thread/inject_items", ThreadInjectItemsParams, scope=MethodScope.THREAD)
THREAD_SHELL_COMMAND = spec(
    "thread/shellCommand",
    scope=MethodScope.THREAD,
    required=["threadId", "command"],
    emits=["turn/started", "item/started", "item/commandExecution/outputDelta", "item/completed", "turn/completed"],
)

COMMAND_EXEC = model_spec(
    "command/exec",
    CommandExecParams,
    scope=MethodScope.PROCESS,
    emits=["command/exec/outputDelta"],
    result_model=PROCESS_METHOD_RESULT_MODELS["command/exec"],
    event_models={
        "command/exec/outputDelta": PROCESS_EVENT_MODELS["command/exec/outputDelta"],
    },
)
COMMAND_EXEC_WRITE = model_spec(
    "command/exec/write",
    CommandExecWriteParams,
    scope=MethodScope.PROCESS,
    result_model=PROCESS_METHOD_RESULT_MODELS["command/exec/write"],
    description="Send stdin data or close stdin on a command/exec process. "
    "At least one of deltaBase64 or closeStdin must be provided.",
)
COMMAND_EXEC_RESIZE = model_spec(
    "command/exec/resize",
    CommandExecResizeParams,
    scope=MethodScope.PROCESS,
    stability=MethodStability.EXPERIMENTAL,
    result_model=PROCESS_METHOD_RESULT_MODELS["command/exec/resize"],
    description="PTY resize is not supported in this version — always returns UNSUPPORTED_FEATURE.",
)
COMMAND_EXEC_TERMINATE = model_spec(
    "command/exec/terminate",
    CommandExecTerminateParams,
    scope=MethodScope.PROCESS,
    result_model=PROCESS_METHOD_RESULT_MODELS["command/exec/terminate"],
)

PROCESS_SPAWN = model_spec(
    "process/spawn",
    ProcessSpawnParams,
    scope=MethodScope.PROCESS,
    emits=["process/outputDelta", "process/exited"],
    result_model=PROCESS_METHOD_RESULT_MODELS["process/spawn"],
    event_models={
        "process/outputDelta": PROCESS_EVENT_MODELS["process/outputDelta"],
        "process/exited": PROCESS_EVENT_MODELS["process/exited"],
    },
)
PROCESS_WRITE_STDIN = model_spec(
    "process/writeStdin",
    ProcessWriteStdinParams,
    scope=MethodScope.PROCESS,
    result_model=PROCESS_METHOD_RESULT_MODELS["process/writeStdin"],
    description="Send stdin data or close stdin on a background process. "
    "At least one of deltaBase64 or closeStdin must be provided.",
)
PROCESS_RESIZE_PTY = model_spec(
    "process/resizePty",
    ProcessResizePtyParams,
    scope=MethodScope.PROCESS,
    stability=MethodStability.EXPERIMENTAL,
    result_model=PROCESS_METHOD_RESULT_MODELS["process/resizePty"],
    description="PTY resize is not supported in this version — always returns UNSUPPORTED_FEATURE.",
)
PROCESS_KILL = model_spec(
    "process/kill",
    ProcessKillParams,
    scope=MethodScope.PROCESS,
    result_model=PROCESS_METHOD_RESULT_MODELS["process/kill"],
)

FS_READ_FILE = model_spec(
    "fs/readFile",
    FsReadFileParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/readFile"],
)
FS_WRITE_FILE = model_spec(
    "fs/writeFile",
    FsWriteFileParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/writeFile"],
)
FS_CREATE_DIRECTORY = model_spec(
    "fs/createDirectory",
    FsCreateDirectoryParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/createDirectory"],
)
FS_GET_METADATA = model_spec(
    "fs/getMetadata",
    FsGetMetadataParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/getMetadata"],
)
FS_READ_DIRECTORY = model_spec(
    "fs/readDirectory",
    FsReadDirectoryParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/readDirectory"],
)
FS_REMOVE = model_spec(
    "fs/remove",
    FsRemoveParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/remove"],
)
FS_COPY = model_spec(
    "fs/copy",
    FsCopyParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/copy"],
)
FS_WATCH = model_spec(
    "fs/watch",
    FsWatchParams,
    scope=MethodScope.FILESYSTEM,
    emits=["fs/changed"],
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/watch"],
    event_models={"fs/changed": FILESYSTEM_EVENT_MODELS["fs/changed"]},
)
FS_UNWATCH = model_spec(
    "fs/unwatch",
    FsUnwatchParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fs/unwatch"],
)

FUZZY_FILE_SEARCH = model_spec(
    "fuzzyFileSearch",
    FuzzyFileSearchParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fuzzyFileSearch"],
)
FUZZY_FILE_SEARCH_SESSION_START = model_spec(
    "fuzzyFileSearch/sessionStart",
    FuzzySessionStartParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fuzzyFileSearch/sessionStart"],
)
FUZZY_FILE_SEARCH_SESSION_UPDATE = model_spec(
    "fuzzyFileSearch/sessionUpdate",
    FuzzySessionUpdateParams,
    scope=MethodScope.FILESYSTEM,
    emits=["fuzzyFileSearch/sessionUpdated", "fuzzyFileSearch/sessionCompleted"],
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fuzzyFileSearch/sessionUpdate"],
    event_models={
        "fuzzyFileSearch/sessionUpdated": FILESYSTEM_EVENT_MODELS["fuzzyFileSearch/sessionUpdated"],
        "fuzzyFileSearch/sessionCompleted": FILESYSTEM_EVENT_MODELS["fuzzyFileSearch/sessionCompleted"],
    },
)
FUZZY_FILE_SEARCH_SESSION_STOP = model_spec(
    "fuzzyFileSearch/sessionStop",
    FuzzySessionStopParams,
    scope=MethodScope.FILESYSTEM,
    result_model=FILESYSTEM_METHOD_RESULT_MODELS["fuzzyFileSearch/sessionStop"],
)

REPLAY_TURNS = spec("replay.turns", scope=MethodScope.DEBUG, required=["threadId"])
REPLAY_TIMELINE = spec("replay.timeline", scope=MethodScope.DEBUG, required=["threadId", "turnId"])
REPLAY_MESSAGES = spec("replay.messages", scope=MethodScope.DEBUG, required=["threadId"])
