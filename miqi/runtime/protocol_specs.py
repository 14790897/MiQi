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


INITIALIZE = spec(
    "initialize",
    scope=MethodScope.CONNECTION,
    required=["clientInfo"],
    emits=[],
    description="Negotiate client identity and capabilities.",
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

COMMAND_EXEC = model_spec("command/exec", CommandExecParams, scope=MethodScope.PROCESS)
COMMAND_EXEC_WRITE = model_spec(
    "command/exec/write",
    CommandExecWriteParams,
    scope=MethodScope.PROCESS,
    description="Send stdin data or close stdin on a command/exec process. "
    "At least one of deltaBase64 or closeStdin must be provided.",
)
COMMAND_EXEC_RESIZE = model_spec(
    "command/exec/resize",
    CommandExecResizeParams,
    scope=MethodScope.PROCESS,
    stability=MethodStability.EXPERIMENTAL,
    description="PTY resize is not supported in this version — always returns UNSUPPORTED_FEATURE.",
)
COMMAND_EXEC_TERMINATE = model_spec("command/exec/terminate", CommandExecTerminateParams, scope=MethodScope.PROCESS)

PROCESS_SPAWN = model_spec("process/spawn", ProcessSpawnParams, scope=MethodScope.PROCESS)
PROCESS_WRITE_STDIN = model_spec(
    "process/writeStdin",
    ProcessWriteStdinParams,
    scope=MethodScope.PROCESS,
    description="Send stdin data or close stdin on a background process. "
    "At least one of deltaBase64 or closeStdin must be provided.",
)
PROCESS_RESIZE_PTY = model_spec(
    "process/resizePty",
    ProcessResizePtyParams,
    scope=MethodScope.PROCESS,
    stability=MethodStability.EXPERIMENTAL,
    description="PTY resize is not supported in this version — always returns UNSUPPORTED_FEATURE.",
)
PROCESS_KILL = model_spec("process/kill", ProcessKillParams, scope=MethodScope.PROCESS)

FS_READ_FILE = model_spec("fs/readFile", FsReadFileParams, scope=MethodScope.FILESYSTEM)
FS_WRITE_FILE = model_spec("fs/writeFile", FsWriteFileParams, scope=MethodScope.FILESYSTEM)
FS_CREATE_DIRECTORY = model_spec("fs/createDirectory", FsCreateDirectoryParams, scope=MethodScope.FILESYSTEM)
FS_GET_METADATA = model_spec("fs/getMetadata", FsGetMetadataParams, scope=MethodScope.FILESYSTEM)
FS_READ_DIRECTORY = model_spec("fs/readDirectory", FsReadDirectoryParams, scope=MethodScope.FILESYSTEM)
FS_REMOVE = model_spec("fs/remove", FsRemoveParams, scope=MethodScope.FILESYSTEM)
FS_COPY = model_spec("fs/copy", FsCopyParams, scope=MethodScope.FILESYSTEM)
FS_WATCH = model_spec("fs/watch", FsWatchParams, scope=MethodScope.FILESYSTEM, emits=["fs/changed"])
FS_UNWATCH = model_spec("fs/unwatch", FsUnwatchParams, scope=MethodScope.FILESYSTEM)

FUZZY_FILE_SEARCH = model_spec("fuzzyFileSearch", FuzzyFileSearchParams, scope=MethodScope.FILESYSTEM)
FUZZY_FILE_SEARCH_SESSION_START = model_spec(
    "fuzzyFileSearch/sessionStart",
    FuzzySessionStartParams,
    scope=MethodScope.FILESYSTEM,
)
FUZZY_FILE_SEARCH_SESSION_UPDATE = model_spec(
    "fuzzyFileSearch/sessionUpdate",
    FuzzySessionUpdateParams,
    scope=MethodScope.FILESYSTEM,
)
FUZZY_FILE_SEARCH_SESSION_STOP = model_spec(
    "fuzzyFileSearch/sessionStop",
    FuzzySessionStopParams,
    scope=MethodScope.FILESYSTEM,
)

REPLAY_TURNS = spec("replay.turns", scope=MethodScope.DEBUG, required=["threadId"])
REPLAY_TIMELINE = spec("replay.timeline", scope=MethodScope.DEBUG, required=["threadId", "turnId"])
REPLAY_MESSAGES = spec("replay.messages", scope=MethodScope.DEBUG, required=["threadId"])
