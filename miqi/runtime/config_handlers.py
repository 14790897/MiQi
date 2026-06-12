"""Config handlers for AppServer dispatch.

Phase 28.3: Migrates config.get and config.update from bridge legacy
handlers to AppServer async handlers. config.update propagates changes
to active RuntimeSessions by updating their SessionState.config_snapshot.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError


async def config_get_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Get current configuration with secrets redacted.

    Returns the full config dict with API key values replaced by hints
    (e.g., "sk-a…b123").
    """
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")

    config = state.load_config()
    data = config.model_dump(by_alias=True)

    # Redact secrets using the bridge's helper
    from miqi.bridge.server import _redact_secrets
    _redact_secrets(data)

    return {"result": data}


async def config_update_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Update configuration and propagate to active sessions.

    1. Deep-merge updates into current config
    2. Validate the merged config
    3. Save to disk
    4. Update AppServer-level config reference
    5. Propagate config snapshot to active RuntimeSessions
    """
    from miqi.config.schema import Config
    from miqi.config.loader import save_config

    import miqi.bridge.server as bridge_module
    from miqi.bridge.server import _deep_merge

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")

    updates = params.get("config", {})
    if not updates:
        raise AppServerError("config is required", code="INVALID_PARAMS")

    current = state.load_config()
    merged = _deep_merge(current.model_dump(by_alias=True), updates)

    # Validate
    try:
        new_config = Config.model_validate(merged)
    except Exception as exc:
        raise AppServerError(
            f"Invalid config: {exc}",
            code="INVALID_PARAMS",
        ) from exc

    # Save to disk
    try:
        save_config(new_config)
    except Exception as exc:
        raise AppServerError(
            f"Failed to save config: {exc}",
            code="INTERNAL",
        ) from exc

    # Update bridge state cache
    state.config = new_config

    # Propagate to active sessions owned by this client
    propagated = 0
    for sid in registry.list_sessions(client_id):
        runtime = await registry.get_session(client_id, sid)
        if runtime is None:
            continue
        try:
            session_state = getattr(runtime.services, "session_state", None)
            if session_state is not None:
                session_state.config_snapshot = new_config
                propagated += 1
        except Exception as exc:
            logger.warning(
                "config.update: failed to propagate to session {}: {}",
                sid, exc,
            )

    logger.info(
        "config.update: saved and propagated to {} session(s) (client={})",
        propagated, client_id,
    )

    return {"result": {"saved": True, "propagated_sessions": propagated}}
