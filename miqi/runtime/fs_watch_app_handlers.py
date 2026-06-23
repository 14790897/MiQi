"""Codex-style fs/watch and fs/unwatch AppServer handlers (Phase 46).

Registers handlers that delegate to ``FsWatchRuntime`` stored in
``registry.bridge_context["fs_watch_runtime"]``.
"""

from __future__ import annotations

from typing import Any

import miqi.runtime.protocol_specs as protocol_specs
from miqi.runtime.app_server import AppServer, AppServerError, get_bridge_context
from miqi.runtime.fs_protocol import resolve_workspace_absolute_path


# ── Handler implementations ──────────────────────────────────────────────────


async def fs_watch_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Handle fs/watch — start watching a filesystem path."""
    runtime = _get_fs_watch_runtime(registry)
    watch_id = params.get("watchId")
    if not isinstance(watch_id, str) or not watch_id.strip():
        raise AppServerError(
            "watchId must be a non-empty string",
            code="INVALID_PARAMS",
        )

    path = resolve_workspace_absolute_path(registry, params.get("path"))
    result = await runtime.watch(client_id, watch_id, path)
    return {"result": result}


async def fs_unwatch_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Handle fs/unwatch — stop watching a filesystem path."""
    runtime = _get_fs_watch_runtime(registry)
    watch_id = params.get("watchId", "")
    if not isinstance(watch_id, str):
        watch_id = ""

    await runtime.unwatch(client_id, watch_id)
    return {"result": {}}


# ── Runtime lookup ───────────────────────────────────────────────────────────


def _get_fs_watch_runtime(registry: Any):
    """Get or lazily create the FsWatchRuntime from bridge_context."""
    from miqi.runtime.fs_watch_runtime import FsWatchRuntime

    runtime = get_bridge_context(registry, "fs_watch_runtime")
    if runtime is None:
        app_server = get_bridge_context(registry, "app_server")
        if app_server is None:
            raise AppServerError(
                "AppServer not available for fs watch runtime",
                code="INTERNAL",
            )
        runtime = FsWatchRuntime(app_server)
        registry.bridge_context["fs_watch_runtime"] = runtime
    return runtime


# ── Registration ─────────────────────────────────────────────────────────────


def register_fs_watch_handlers(server: AppServer) -> None:
    """Register fs/watch and fs/unwatch handlers on *server*."""
    server.register_method("fs/watch", fs_watch_handler, spec=protocol_specs.FS_WATCH)
    server.register_method("fs/unwatch", fs_unwatch_handler, spec=protocol_specs.FS_UNWATCH)
