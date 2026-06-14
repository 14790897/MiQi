"""Channel handlers for AppServer dispatch.

Phase 35.2: Migrates channels.list and channels.update from bridge
legacy handlers to AppServer async handlers.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError


async def channels_list_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Return current channels config with secrets redacted."""
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")

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

    import miqi.bridge.server as bridge_module
    from miqi.bridge.server import _deep_merge

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")

    config = state.load_config()
    current = config.channels.model_dump(by_alias=False)
    merged = _deep_merge(current, updates)
    config.channels = ChannelsConfig.model_validate(merged)
    save_config(config)
    state.config = config

    return {"result": {"saved": True}}
