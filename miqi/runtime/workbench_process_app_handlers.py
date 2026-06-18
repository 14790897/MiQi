"""Codex-style process/* AppServer handlers.

Registers: process/spawn, process/writeStdin, process/resizePty,
process/kill.

process/spawn is gated behind experimentalApi.  All process output
flows through client-scoped events (process/outputDelta, process/exited).

Phase 43: no PTY support. tty:true and resizePty return UNSUPPORTED_FEATURE.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from miqi.runtime.app_server import (
    AppServer,
    AppServerError,
    get_bridge_context,
)
from miqi.runtime.workbench_command_app_handlers import (
    _decode_base64,
    _resolve_cwd,
    _safe_handle_id,
    _validate_argv,
    _validate_env,
)
from miqi.runtime.workbench_process_runtime import (
    DEFAULT_OUTPUT_BYTES_CAP,
    DEFAULT_TIMEOUT_MS,
    HandleNotFoundError,
    OutputChunk,
    ProcessExit,
    WorkbenchProcessError,
    WorkbenchProcessRuntime,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _require_experimental_api(
    params: dict[str, Any],
    registry: Any,
    client_id: str,
) -> None:
    """Gate process/spawn behind experimentalApi flag.

    Phase 45: Checks in priority order:
    1. AppServer client capabilities (from initialize handshake)
    2. params.experimentalApi == True (backwards compatible)
    3. bridge_context["experimental_api_enabled"] == True (test/dev fallback)
    """
    # 1. Connection capabilities from initialize
    app_server = get_bridge_context(registry, "app_server")
    if app_server is not None and hasattr(app_server, "is_experimental_enabled"):
        if app_server.is_experimental_enabled(client_id):
            return

    # 2. Per-request params flag (backwards compatible)
    if params.get("experimentalApi") is True:
        return

    # 3. Bridge context flag (test/dev fallback)
    ctx_enabled = get_bridge_context(registry, "experimental_api_enabled")
    if ctx_enabled is True:
        return

    raise AppServerError(
        "process/spawn requires experimentalApi: true",
        code="EXPERIMENTAL_API_REQUIRED",
    )


def _get_wpr(registry: Any) -> WorkbenchProcessRuntime:
    """Get or lazily create the WorkbenchProcessRuntime from bridge_context."""
    wpr = get_bridge_context(registry, "workbench_process_runtime")
    if wpr is None:
        state = get_bridge_context(registry, "state")
        workspace = Path.cwd()
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


def register_workbench_process_handlers(server: AppServer) -> None:
    """Register process/* handlers on an AppServer instance."""

    # ── process/spawn ───────────────────────────────────────────────────

    async def _process_spawn(request_id, params, client_id, session_id, registry):
        wpr = _get_wpr(registry)

        # Experimental gate
        _require_experimental_api(params, registry, client_id)

        # Reject tty early
        if params.get("tty") is True:
            raise AppServerError(
                "PTY is not supported in this version",
                code="UNSUPPORTED_FEATURE",
            )

        command = _validate_argv(params.get("command"))
        process_handle = _safe_handle_id(
            params.get("processHandle"), param_name="processHandle",
        )

        cwd_raw = params.get("cwd")
        if cwd_raw is None:
            raise AppServerError(
                "cwd is required for process/spawn",
                code="INVALID_PARAMS",
            )
        cwd = _resolve_cwd(cwd_raw, wpr.workspace)

        env = _validate_env(params.get("env"))

        # ── output cap / disableOutputCap ──────────────────────────────
        disable_output_cap = params.get("disableOutputCap", False)
        if not isinstance(disable_output_cap, bool):
            raise AppServerError(
                "disableOutputCap must be a boolean",
                code="INVALID_PARAMS",
            )
        output_cap = params.get("outputBytesCap")
        if "outputBytesCap" not in params:
            output_cap_int: int | None = DEFAULT_OUTPUT_BYTES_CAP
        elif disable_output_cap:
            raise AppServerError(
                "disableOutputCap and outputBytesCap are mutually exclusive",
                code="INVALID_PARAMS",
            )
        elif output_cap is None:
            raise AppServerError(
                "outputBytesCap must not be null",
                code="INVALID_PARAMS",
            )
        elif not isinstance(output_cap, (int, float)):
            raise AppServerError(
                "outputBytesCap must be a number",
                code="INVALID_PARAMS",
            )
        else:
            output_cap_int = int(output_cap)
            if output_cap_int < 0:
                raise AppServerError(
                    "outputBytesCap must be >= 0",
                    code="INVALID_PARAMS",
                )
        if disable_output_cap:
            output_cap_int = None

        # ── timeout / disableTimeout ──────────────────────────────────
        disable_timeout = params.get("disableTimeout", False)
        if not isinstance(disable_timeout, bool):
            raise AppServerError(
                "disableTimeout must be a boolean",
                code="INVALID_PARAMS",
            )
        if "timeoutMs" in params:
            # timeoutMs is present (regardless of value type — null or number)
            if disable_timeout:
                raise AppServerError(
                    "disableTimeout and timeoutMs are mutually exclusive",
                    code="INVALID_PARAMS",
                )
            timeout_ms_raw = params["timeoutMs"]
            if timeout_ms_raw is None:
                # null means no timeout for process/spawn (long-running servers)
                timeout_ms_int: int | None = None
            elif not isinstance(timeout_ms_raw, (int, float)):
                raise AppServerError(
                    "timeoutMs must be a number",
                    code="INVALID_PARAMS",
                )
            else:
                timeout_ms_int = int(timeout_ms_raw)
                if timeout_ms_int < 0:
                    raise AppServerError(
                        "timeoutMs must be >= 0",
                        code="INVALID_PARAMS",
                    )
        else:
            timeout_ms_int: int | None = (
                None if disable_timeout else DEFAULT_TIMEOUT_MS
            )

        stream_stdout_stderr = params.get("streamStdoutStderr", True)
        stdin_enabled = bool(stream_stdout_stderr)  # default true for spawn

        # Streaming callback
        async def _on_chunk(handle_id: str, chunk: OutputChunk) -> None:
            if stream_stdout_stderr:
                await server.emit_client_event(
                    client_id,
                    "process/outputDelta",
                    {
                        "processHandle": handle_id,
                        "stream": chunk.stream,
                        "deltaBase64": base64.b64encode(chunk.data).decode("ascii"),
                        "capReached": chunk.cap_reached,
                    },
                    request_id=request_id,
                )

        # Exit callback — emits process/exited notification
        async def _on_exit(exit_result: ProcessExit) -> None:
            await server.emit_client_event(
                client_id,
                "process/exited",
                {
                    "processHandle": exit_result.handle_id,
                    "exitCode": exit_result.exit_code,
                    "stdout": exit_result.stdout,
                    "stderr": exit_result.stderr,
                    "stdoutCapReached": exit_result.stdout_cap_reached,
                    "stderrCapReached": exit_result.stderr_cap_reached,
                    "durationMs": exit_result.duration_ms,
                    "terminationReason": exit_result.termination_reason,
                },
                request_id=request_id,
            )

        try:
            await wpr.spawn_background(
                client_id=client_id,
                handle_id=process_handle,
                kind="process",
                command=command,
                cwd=cwd,
                env=env,
                stdin_enabled=stdin_enabled,
                output_cap=output_cap_int,
                timeout_ms=timeout_ms_int,
                on_chunk=_on_chunk if stream_stdout_stderr else None,
                on_exit=_on_exit,
            )
        except WorkbenchProcessError as exc:
            raise AppServerError(exc.args[0], code=exc.code)

        return {"result": {}}

    # ── process/writeStdin ──────────────────────────────────────────────

    async def _process_write_stdin(request_id, params, client_id, session_id, registry):
        wpr = _get_wpr(registry)
        process_handle = _safe_handle_id(
            params.get("processHandle"), param_name="processHandle",
        )

        delta_b64 = params.get("deltaBase64")
        close_stdin = params.get("closeStdin", False)

        if not delta_b64 and not close_stdin:
            raise AppServerError(
                "At least one of deltaBase64 or closeStdin is required",
                code="INVALID_PARAMS",
            )

        if delta_b64:
            data = _decode_base64(delta_b64)
            try:
                await wpr.write_stdin(client_id, process_handle, data)
            except WorkbenchProcessError as exc:
                raise AppServerError(exc.args[0], code=exc.code)

        if close_stdin:
            try:
                await wpr.close_stdin(client_id, process_handle)
            except WorkbenchProcessError as exc:
                raise AppServerError(exc.args[0], code=exc.code)

        return {"result": {}}

    # ── process/resizePty ───────────────────────────────────────────────

    async def _process_resize_pty(request_id, params, client_id, session_id, registry):
        raise AppServerError(
            "PTY is not supported in this version",
            code="UNSUPPORTED_FEATURE",
        )

    # ── process/kill ────────────────────────────────────────────────────

    async def _process_kill(request_id, params, client_id, session_id, registry):
        wpr = _get_wpr(registry)
        process_handle = _safe_handle_id(
            params.get("processHandle"), param_name="processHandle",
        )

        try:
            await wpr.kill(client_id, process_handle)
        except HandleNotFoundError:
            raise AppServerError(
                f"Process handle not found: {process_handle}",
                code="NOT_FOUND",
            )
        except WorkbenchProcessError as exc:
            raise AppServerError(exc.args[0], code=exc.code)

        return {"result": {}}

    # ── Register all ────────────────────────────────────────────────────

    server.register_method("process/spawn", _process_spawn)
    server.register_method("process/writeStdin", _process_write_stdin)
    server.register_method("process/resizePty", _process_resize_pty)
    server.register_method("process/kill", _process_kill)
