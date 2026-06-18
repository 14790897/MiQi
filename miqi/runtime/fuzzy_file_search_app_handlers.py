"""Codex-style fuzzyFileSearch* AppServer handlers (Phase 46).

Registers: fuzzyFileSearch, fuzzyFileSearch/sessionStart,
fuzzyFileSearch/sessionUpdate, fuzzyFileSearch/sessionStop.

Session methods are gated behind ``experimentalApi`` via the shared
``require_experimental_api()`` gate from Phase 46.  One-shot
``fuzzyFileSearch`` does NOT require experimental API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.runtime.app_server import AppServer, AppServerError, get_bridge_context
from miqi.runtime.experimental_api import require_experimental_api
from miqi.runtime.fs_protocol import resolve_workspace_absolute_path


# ── Handler implementations ──────────────────────────────────────────────────


async def fuzzy_file_search_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Handle fuzzyFileSearch — one-shot file search (no experimental gate)."""
    runtime = _get_fuzzy_runtime(registry)

    query = params.get("query")
    if not isinstance(query, str):
        raise AppServerError(
            "query must be a string",
            code="INVALID_PARAMS",
        )

    raw_roots = params.get("roots")
    if not isinstance(raw_roots, list):
        raise AppServerError(
            "roots must be a list",
            code="INVALID_PARAMS",
        )

    roots: list[Path] = []
    for raw in raw_roots:
        try:
            resolved = resolve_workspace_absolute_path(
                registry, raw, field_name="root",
            )
            roots.append(resolved)
        except AppServerError:
            # Escaping roots return INVALID_PARAMS, missing roots are skipped
            continue

    if not roots:
        # No valid roots → empty result
        return {"result": {"files": []}}

    files = runtime.search(query, roots)
    return {"result": {"files": files}}


async def fuzzy_session_start_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Handle fuzzyFileSearch/sessionStart — requires experimentalApi."""
    require_experimental_api(params, registry, client_id, "fuzzyFileSearch/sessionStart")
    runtime = _get_fuzzy_runtime(registry)

    sid = params.get("sessionId")
    if not isinstance(sid, str) or not sid.strip():
        raise AppServerError(
            "sessionId must be a non-empty string",
            code="INVALID_PARAMS",
        )

    raw_roots = params.get("roots")
    if not isinstance(raw_roots, list):
        raise AppServerError(
            "roots must be a list",
            code="INVALID_PARAMS",
        )

    roots: list[Path] = []
    for raw in raw_roots:
        try:
            resolved = resolve_workspace_absolute_path(
                registry, raw, field_name="root",
            )
            roots.append(resolved)
        except AppServerError:
            # Escaping roots return INVALID_PARAMS, missing roots are skipped
            continue

    runtime.session_start(client_id, sid, roots)
    return {"result": {}}


async def fuzzy_session_update_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Handle fuzzyFileSearch/sessionUpdate — requires experimentalApi."""
    require_experimental_api(params, registry, client_id, "fuzzyFileSearch/sessionUpdate")
    runtime = _get_fuzzy_runtime(registry)

    sid = params.get("sessionId")
    if not isinstance(sid, str) or not sid.strip():
        raise AppServerError(
            "sessionId must be a non-empty string",
            code="INVALID_PARAMS",
        )

    query = params.get("query")
    if not isinstance(query, str):
        raise AppServerError(
            "query must be a string",
            code="INVALID_PARAMS",
        )

    try:
        await runtime.session_update(client_id, sid, query)
    except KeyError:
        raise AppServerError(
            f"Unknown session: {sid}",
            code="INVALID_PARAMS",
        )

    return {"result": {}}


async def fuzzy_session_stop_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Handle fuzzyFileSearch/sessionStop — requires experimentalApi."""
    require_experimental_api(params, registry, client_id, "fuzzyFileSearch/sessionStop")
    runtime = _get_fuzzy_runtime(registry)

    sid = params.get("sessionId", "")
    if not isinstance(sid, str):
        sid = ""

    runtime.session_stop(client_id, sid)
    return {"result": {}}


# ── Runtime lookup ───────────────────────────────────────────────────────────


def _get_fuzzy_runtime(registry: Any):
    """Get or lazily create the FuzzyFileSearchRuntime from bridge_context."""
    from miqi.runtime.fuzzy_file_search_runtime import FuzzyFileSearchRuntime

    runtime = get_bridge_context(registry, "fuzzy_file_search_runtime")
    if runtime is None:
        app_server = get_bridge_context(registry, "app_server")
        if app_server is None:
            raise AppServerError(
                "AppServer not available for fuzzy search runtime",
                code="INTERNAL",
            )
        runtime = FuzzyFileSearchRuntime(app_server)
        registry.bridge_context["fuzzy_file_search_runtime"] = runtime
    return runtime


# ── Registration ─────────────────────────────────────────────────────────────


def register_fuzzy_file_search_handlers(server: AppServer) -> None:
    """Register fuzzyFileSearch* handlers on *server*."""
    server.register_method("fuzzyFileSearch", fuzzy_file_search_handler)
    server.register_method("fuzzyFileSearch/sessionStart", fuzzy_session_start_handler)
    server.register_method("fuzzyFileSearch/sessionUpdate", fuzzy_session_update_handler)
    server.register_method("fuzzyFileSearch/sessionStop", fuzzy_session_stop_handler)
