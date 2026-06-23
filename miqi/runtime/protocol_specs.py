"""Explicit App Server protocol specs for high-value Codex-style methods."""

from __future__ import annotations

from typing import Any

from miqi.runtime.protocol_registry import (
    MethodScope,
    MethodStability,
    ProtocolMethodSpec,
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

TURN_START = spec(
    "turn/start",
    scope=MethodScope.TURN,
    required=["threadId", "input"],
    emits=["turn/started", "item/started", "item/completed", "turn/completed"],
)
TURN_INTERRUPT = spec("turn/interrupt", scope=MethodScope.TURN, required=["threadId", "turnId"])
TURN_STEER = spec("turn/steer", scope=MethodScope.TURN, required=["threadId", "expectedTurnId", "input"])
THREAD_COMPACT_START = spec(
    "thread/compact/start",
    scope=MethodScope.THREAD,
    required=["threadId"],
    emits=["turn/started", "item/started", "item/completed", "turn/completed"],
)
THREAD_INJECT_ITEMS = spec("thread/inject_items", scope=MethodScope.THREAD, required=["threadId", "items"])
THREAD_SHELL_COMMAND = spec(
    "thread/shellCommand",
    scope=MethodScope.THREAD,
    required=["threadId", "command"],
    emits=["turn/started", "item/started", "item/commandExecution/outputDelta", "item/completed", "turn/completed"],
)

COMMAND_EXEC = spec("command/exec", scope=MethodScope.PROCESS, required=["cmd"])
COMMAND_EXEC_WRITE = spec("command/exec/write", scope=MethodScope.PROCESS, required=["execId", "data"])
COMMAND_EXEC_RESIZE = spec("command/exec/resize", scope=MethodScope.PROCESS, required=["execId", "cols", "rows"])
COMMAND_EXEC_TERMINATE = spec("command/exec/terminate", scope=MethodScope.PROCESS, required=["execId"])

PROCESS_SPAWN = spec("process/spawn", scope=MethodScope.PROCESS, required=["cmd"])
PROCESS_WRITE_STDIN = spec("process/writeStdin", scope=MethodScope.PROCESS, required=["processId", "data"])
PROCESS_RESIZE_PTY = spec("process/resizePty", scope=MethodScope.PROCESS, required=["processId", "cols", "rows"])
PROCESS_KILL = spec("process/kill", scope=MethodScope.PROCESS, required=["processId"])

FS_READ_FILE = spec("fs/readFile", scope=MethodScope.FILESYSTEM, required=["path"])
FS_WRITE_FILE = spec("fs/writeFile", scope=MethodScope.FILESYSTEM, required=["path", "content"])
FS_CREATE_DIRECTORY = spec("fs/createDirectory", scope=MethodScope.FILESYSTEM, required=["path"])
FS_GET_METADATA = spec("fs/getMetadata", scope=MethodScope.FILESYSTEM, required=["path"])
FS_READ_DIRECTORY = spec("fs/readDirectory", scope=MethodScope.FILESYSTEM, required=["path"])
FS_REMOVE = spec("fs/remove", scope=MethodScope.FILESYSTEM, required=["path"])
FS_COPY = spec("fs/copy", scope=MethodScope.FILESYSTEM, required=["sourcePath", "destinationPath"])
FS_WATCH = spec("fs/watch", scope=MethodScope.FILESYSTEM, required=["path"], emits=["fs/changed"])
FS_UNWATCH = spec("fs/unwatch", scope=MethodScope.FILESYSTEM, required=["watchId"])

FUZZY_FILE_SEARCH = spec("fuzzyFileSearch", scope=MethodScope.FILESYSTEM, required=["query"])
FUZZY_FILE_SEARCH_SESSION_START = spec("fuzzyFileSearch/sessionStart", scope=MethodScope.FILESYSTEM)
FUZZY_FILE_SEARCH_SESSION_UPDATE = spec("fuzzyFileSearch/sessionUpdate", scope=MethodScope.FILESYSTEM, required=["sessionId", "query"])
FUZZY_FILE_SEARCH_SESSION_STOP = spec("fuzzyFileSearch/sessionStop", scope=MethodScope.FILESYSTEM, required=["sessionId"])

REPLAY_TURNS = spec("replay.turns", scope=MethodScope.DEBUG, required=["thread_id"])
REPLAY_TIMELINE = spec("replay.timeline", scope=MethodScope.DEBUG, required=["thread_id", "turn_id"])
REPLAY_MESSAGES = spec("replay.messages", scope=MethodScope.DEBUG, required=["thread_id"])
