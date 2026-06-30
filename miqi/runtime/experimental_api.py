"""Shared experimental API gate for Codex experimental methods (Phase 46).

Provides ``require_experimental_api()`` — a single gate function that
experimental handlers call before executing their logic.  Checks, in
priority order:

1. AppServer client capabilities (from initialize handshake)
2. Per-request ``params.experimentalApi == True``
3. ``registry.bridge_context["experimental_api_enabled"] == True``

If none of the gates pass, raises ``AppServerError`` with code
``EXPERIMENTAL_API_REQUIRED``.
"""

from __future__ import annotations

from typing import Any

from miqi.runtime.app_server import AppServerError, get_bridge_context


def require_experimental_api(
    params: dict[str, Any],
    registry: Any,
    client_id: str,
    method: str,
) -> None:
    """Require experimental API access for *method*.

    Raises :exc:`AppServerError` with ``EXPERIMENTAL_API_REQUIRED`` if
    none of the experimental gates are satisfied.
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
    if get_bridge_context(registry, "experimental_api_enabled") is True:
        return

    raise AppServerError(
        f"{method} requires experimentalApi: true",
        code="EXPERIMENTAL_API_REQUIRED",
    )
