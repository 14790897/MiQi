"""Codex-style command/exec* AppServer handlers.

Registers: command/exec, command/exec/write, command/exec/resize,
command/exec/terminate.

All process execution flows through WorkbenchProcessRuntime, which is
stored in registry.bridge_context["workbench_process_runtime"].
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

import miqi.runtime.protocol_specs as protocol_specs
from miqi.runtime.app_server import (
    AppServer,
    AppServerError,
    get_bridge_context,
)
from miqi.runtime.process_request_models import (
    CommandExecParams,
    CommandExecResizeParams,
    CommandExecTerminateParams,
    CommandExecWriteParams,
    validate_process_params,
)
from miqi.runtime.workbench_process_runtime import (
    BLOCKED_ENV_PREFIXES,
    DEFAULT_OUTPUT_BYTES_CAP,
    DEFAULT_TIMEOUT_MS,
    HandleNotFoundError,
    OutputChunk,
    WorkbenchProcessError,
    WorkbenchProcessRuntime,
)


# ── Validation helpers ───────────────────────────────────────────────────


def _safe_handle_id(raw: Any, param_name: str = "processId") -> str:
    """Validate a process/handle ID string.

    Rules:
    - must be a non-empty string
    - max length 128
    - allowed chars: [A-Za-z0-9_.:-]
    - no slash or backslash
    - no ".."
    """
    if not isinstance(raw, str) or not raw:
        raise AppServerError(
            f"{param_name} must be a non-empty string",
            code="INVALID_PARAMS",
        )
    if len(raw) > 128:
        raise AppServerError(
            f"{param_name} must be <= 128 characters",
            code="INVALID_PARAMS",
        )
    # Check for disallowed characters
    for ch in raw:
        if ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-":
            raise AppServerError(
                f"{param_name} contains invalid character: {ch!r}",
                code="INVALID_PARAMS",
            )
    if "/" in raw or "\\" in raw:
        raise AppServerError(
            f"{param_name} must not contain slashes",
            code="INVALID_PARAMS",
        )
    if ".." in raw:
        raise AppServerError(
            f"{param_name} must not contain '..'",
            code="INVALID_PARAMS",
        )
    return raw


def _validate_argv(raw: Any) -> list[str]:
    """Validate command argv list.

    - must be a non-empty list
    - every element must be a non-empty string
    """
    if not isinstance(raw, list) or len(raw) == 0:
        raise AppServerError(
            "command must be a non-empty list of strings",
            code="INVALID_PARAMS",
        )
    for i, arg in enumerate(raw):
        if not isinstance(arg, str) or not arg:
            raise AppServerError(
                f"command[{i}] must be a non-empty string",
                code="INVALID_PARAMS",
            )
    return raw


def _validate_env(raw: Any) -> dict[str, str | None] | None:
    """Validate optional env dict.

    Only allows environment variables that do not start with
    known-dangerous prefixes (dynamic linker, language runtime
    injection vectors).  Unknown/blocked keys are rejected with
    INVALID_PARAMS.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise AppServerError(
            "env must be a dict of string -> string|null",
            code="INVALID_PARAMS",
        )
    for key, value in raw.items():
        if not isinstance(key, str):
            raise AppServerError(
                "env keys must be strings",
                code="INVALID_PARAMS",
            )
        if value is not None and not isinstance(value, str):
            raise AppServerError(
                f"env['{key}'] must be a string or null",
                code="INVALID_PARAMS",
            )
        # Security: reject dangerous environment variable prefixes
        for prefix in BLOCKED_ENV_PREFIXES:
            if key.upper().startswith(prefix.upper()):
                raise AppServerError(
                    f"env key {key!r} is not allowed for security reasons",
                    code="INVALID_PARAMS",
                )
    return raw


def _resolve_cwd(raw: Any, workspace: Path) -> Path:
    """Validate and resolve cwd parameter.

    - If None/omitted, use workspace root.
    - Must be an absolute path.
    - By default, must be inside workspace.
    """
    if raw is None:
        return workspace
    if not isinstance(raw, str) or not raw:
        raise AppServerError(
            "cwd must be a non-empty string",
            code="INVALID_PARAMS",
        )
    cwd = Path(raw)
    if not cwd.is_absolute():
        raise AppServerError(
            "cwd must be an absolute path",
            code="INVALID_PARAMS",
        )
    if not cwd.exists():
        raise AppServerError(
            f"cwd does not exist: {cwd}",
            code="INVALID_PARAMS",
        )
    if not cwd.is_dir():
        raise AppServerError(
            f"cwd is not a directory: {cwd}",
            code="INVALID_PARAMS",
        )
    # Default safety: cwd must be inside workspace
    try:
        cwd.resolve().relative_to(workspace.resolve())
    except ValueError:
        raise AppServerError(
            f"cwd is outside workspace: {cwd}",
            code="INVALID_PARAMS",
        )
    return cwd


def _decode_base64(raw: Any, param_name: str = "deltaBase64") -> bytes:
    """Decode a base64-encoded string, raising INVALID_PARAMS on failure."""
    if not isinstance(raw, str):
        raise AppServerError(
            f"{param_name} must be a base64-encoded string",
            code="INVALID_PARAMS",
        )
    try:
        return base64.b64decode(raw, validate=True)
    except Exception:
        raise AppServerError(
            f"{param_name} is not valid base64",
            code="INVALID_PARAMS",
        )


def _get_wpr(registry: Any) -> WorkbenchProcessRuntime:
    """Get or lazily create the WorkbenchProcessRuntime from bridge_context."""
    wpr = get_bridge_context(registry, "workbench_process_runtime")
    if wpr is None:
        # Determine workspace from bridge state or fall back to cwd
        from pathlib import Path as _Path
        state = get_bridge_context(registry, "state")
        workspace = _Path.cwd()
        if state is not None:
            try:
                config = state.load_config()
                workspace = config.workspace_path
            except Exception:
                pass
        wpr = WorkbenchProcessRuntime(workspace=workspace)
        registry.bridge_context["workbench_process_runtime"] = wpr
    return wpr


# ── Registration ─────────────────────────────────────────────────────────


def register_workbench_command_handlers(server: AppServer) -> None:
    """Register command/exec* handlers on an AppServer instance."""

    # ── command/exec ────────────────────────────────────────────────────

    async def _command_exec(request_id, params, client_id, session_id, registry):
        wpr = _get_wpr(registry)

        # Preserve UNSUPPORTED_FEATURE for tty before typed validation
        if params.get("tty") is True:
            raise AppServerError(
                "PTY is not supported in this version",
                code="UNSUPPORTED_FEATURE",
            )

        typed = validate_process_params(CommandExecParams, params, workspace=wpr.workspace)

        # Streaming callback
        async def _on_chunk(handle_id: str, chunk: OutputChunk) -> None:
            await server.emit_client_event(
                client_id,
                "command/exec/outputDelta",
                {
                    "processId": handle_id,
                    "stream": chunk.stream,
                    "deltaBase64": base64.b64encode(chunk.data).decode("ascii"),
                    "capReached": chunk.cap_reached,
                },
                request_id=request_id,
            )

        on_chunk = _on_chunk if typed.stream_stdout_stderr else None
        handle_id = typed.process_id or f"cmd-internal-{uuid.uuid4().hex}"

        try:
            exit_result = await wpr.spawn(
                client_id=client_id,
                handle_id=handle_id,
                kind="commandExec",
                command=typed.command,
                cwd=typed.cwd,
                env=typed.env,
                stdin_enabled=typed.stdin_enabled,
                output_cap=typed.output_cap,
                timeout_ms=typed.timeout_ms,
                on_chunk=on_chunk,
                client_visible=typed.client_visible,
            )
        except WorkbenchProcessError as exc:
            raise AppServerError(exc.args[0], code=exc.code)

        return {
            "result": {
                "exitCode": exit_result.exit_code,
                "stdout": exit_result.stdout,
                "stderr": exit_result.stderr,
                "stdoutCapReached": exit_result.stdout_cap_reached,
                "stderrCapReached": exit_result.stderr_cap_reached,
                "durationMs": exit_result.duration_ms,
                "terminationReason": exit_result.termination_reason,
            },
        }

    # ── command/exec/write ──────────────────────────────────────────────

    async def _command_exec_write(request_id, params, client_id, session_id, registry):
        wpr = _get_wpr(registry)
        typed = validate_process_params(CommandExecWriteParams, params)

        if typed.delta_bytes is not None:
            try:
                await wpr.write_stdin(
                    client_id,
                    typed.process_id,
                    typed.delta_bytes,
                    require_client_visible=True,
                )
            except WorkbenchProcessError as exc:
                raise AppServerError(exc.args[0], code=exc.code)

        if typed.close_stdin:
            try:
                await wpr.close_stdin(
                    client_id,
                    typed.process_id,
                    require_client_visible=True,
                )
            except WorkbenchProcessError as exc:
                raise AppServerError(exc.args[0], code=exc.code)

        return {"result": {}}

    # ── command/exec/resize ─────────────────────────────────────────────

    async def _command_exec_resize(request_id, params, client_id, session_id, registry):
        validate_process_params(CommandExecResizeParams, params)
        raise AppServerError(
            "PTY is not supported in this version",
            code="UNSUPPORTED_FEATURE",
        )

    # ── command/exec/terminate ───────────────────────────────────────────

    async def _command_exec_terminate(request_id, params, client_id, session_id, registry):
        wpr = _get_wpr(registry)
        typed = validate_process_params(CommandExecTerminateParams, params)

        try:
            await wpr.kill(client_id, typed.process_id, require_client_visible=True)
        except HandleNotFoundError:
            raise AppServerError(
                f"Process not found: {typed.process_id}",
                code="NOT_FOUND",
            )
        except WorkbenchProcessError as exc:
            raise AppServerError(exc.args[0], code=exc.code)

        return {"result": {}}

    # ── Register all ────────────────────────────────────────────────────

    server.register_method("command/exec", _command_exec, spec=protocol_specs.COMMAND_EXEC)
    server.register_method("command/exec/write", _command_exec_write, spec=protocol_specs.COMMAND_EXEC_WRITE)
    server.register_method("command/exec/resize", _command_exec_resize, spec=protocol_specs.COMMAND_EXEC_RESIZE)
    server.register_method("command/exec/terminate", _command_exec_terminate, spec=protocol_specs.COMMAND_EXEC_TERMINATE)
