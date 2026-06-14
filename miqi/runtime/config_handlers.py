"""Config handlers for AppServer dispatch.

Phase 28.3: Migrates config.get and config.update from bridge legacy
handlers to AppServer async handlers. config.update propagates changes
to active RuntimeSessions by updating their SessionState.config_snapshot.

Phase 38.5: Removed direct import of miqi.bridge.server. Uses
get_bridge_state(registry) for DI and shared helpers from
config_app_handlers for redaction and deep merge.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError, get_bridge_state


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
    from miqi.runtime.config_app_handlers import _redact_secrets

    state = get_bridge_state(registry)
    config = state.load_config()
    data = config.model_dump(by_alias=True)
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

    from miqi.runtime.config_app_handlers import _deep_merge

    state = get_bridge_state(registry)
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
