"""Permission handlers for AppServer dispatch.

Phase 35.2: Migrates permissions.get, permissions.update,
permissions.permanent.add, and permissions.permanent.remove from bridge
legacy handlers to AppServer async handlers.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError


def _get_orchestrator() -> Any:
    """Get the global ToolOrchestrator from bridge state."""
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        return None
    return getattr(state, "_orchestrator", None)


async def permissions_get_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Return current permission engine configuration.

    Returns filesystem rules, network policy, exec approval mode,
    permanent allowlist, and deny patterns.
    """
    orch = _get_orchestrator()
    if orch is not None:
        pe = orch.permissions
        return {"result": {
            "filesystem": {"rules": [], "default_mode": "read"},
            "network": "allow_all",
            "exec_approval": "dangerous",
            "permanent_allowlist": list(pe.permanent_allowlist),
            "deny_patterns": list(pe.deny_patterns),
        }}

    return {"result": {
        "filesystem": {"rules": [], "default_mode": "read"},
        "network": "allow_all",
        "exec_approval": "dangerous",
        "permanent_allowlist": [],
        "deny_patterns": [],
    }}


async def permissions_update_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Update permission engine deny/allow patterns.

    Accepts config.deny_patterns and config.permanent_allowlist as lists.
    Converted to sets internally for efficient lookup.
    """
    cfg = params.get("config", {})
    orch = _get_orchestrator()
    if orch is not None:
        pe = orch.permissions
        if "permanent_allowlist" in cfg:
            pe.permanent_allowlist = set(cfg["permanent_allowlist"])
        if "deny_patterns" in cfg:
            pe.deny_patterns = set(cfg["deny_patterns"])

    return {"result": {"saved": True}}


async def permissions_permanent_add_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Add a pattern to the permanent allowlist."""
    pattern = params.get("pattern", "")
    orch = _get_orchestrator()
    if orch is not None and pattern:
        orch.permissions.permanent_allowlist.add(pattern)

    return {"result": {"added": bool(pattern)}}


async def permissions_permanent_remove_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Remove a pattern from the permanent allowlist."""
    pattern = params.get("pattern", "")
    orch = _get_orchestrator()
    if orch is not None and pattern:
        orch.permissions.permanent_allowlist.discard(pattern)

    return {"result": {"removed": bool(pattern)}}
