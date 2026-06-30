"""Channel handlers for AppServer dispatch.

Phase 35.2: Migrates channels.list and channels.update from bridge
legacy handlers to AppServer async handlers.

Phase 35 hardening: Uses get_bridge_state(registry) for DI instead of
importing miqi.bridge.server directly.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError, get_bridge_state


async def channels_list_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Return current channels config with secrets redacted."""
    state = get_bridge_state(registry)
    config = state.load_config()
    data = config.channels.model_dump(by_alias=False)
    from miqi.bridge.server import _redact_secrets
    _redact_secrets(data)

    return {"result": {"channels": data}}


async def channels_update_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Merge partial update into channels config and save."""
    from miqi.config.loader import save_config
    from miqi.config.schema import ChannelsConfig

    updates = params.get("channels", {})
    if not isinstance(updates, dict):
        raise AppServerError("channels must be a dict", code="INVALID_PARAMS")

    from miqi.bridge.server import _deep_merge

    state = get_bridge_state(registry)
    config = state.load_config()
    current = config.channels.model_dump(by_alias=False)
    merged = _deep_merge(current, updates)
    config.channels = ChannelsConfig.model_validate(merged)
    save_config(config)
    state.config = config

    return {"result": {"saved": True}}
