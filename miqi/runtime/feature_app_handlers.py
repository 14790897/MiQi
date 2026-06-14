"""Codex-style experimental feature AppServer handlers."""

from __future__ import annotations

from typing import Any

from miqi.runtime.app_server import AppServer, get_bridge_context
from miqi.runtime.feature_runtime import FeatureRuntime


def _get_feature_runtime(registry: Any) -> FeatureRuntime:
    fr = get_bridge_context(registry, "feature_runtime", None)
    if fr is None:
        fr = FeatureRuntime()
        registry.bridge_context["feature_runtime"] = fr
    return fr


def register_feature_app_handlers(server: AppServer) -> None:

    async def _experimental_feature_list(request_id, params, client_id, session_id, registry):
        """experimentalFeature/list — paginated feature catalog.

        Params:
            cursor: str | None
            limit: int = 100
            threadId: str | None (ignored in this implementation)
        Response:
            {"data": [...], "nextCursor": str|None}
        """
        fr = _get_feature_runtime(registry)
        cursor = params.get("cursor")
        limit = int(params.get("limit", 100))
        page = fr.list_features(cursor=cursor, limit=limit)
        return {"result": page}

    async def _experimental_feature_enablement_set(request_id, params, client_id, session_id, registry):
        """experimentalFeature/enablement/set — toggle feature overrides.

        Params:
            features: dict[str, bool]  or  enablement: dict[str, bool]
        Response:
            {"saved": True, "ignored": [...]}
        """
        fr = _get_feature_runtime(registry)
        features = params.get("features") or params.get("enablement") or {}
        if not isinstance(features, dict):
            features = {}
        ignored = fr.set_enablement(features)
        return {"result": {"saved": True, "ignored": ignored}}

    server.register_method("experimentalFeature/list", _experimental_feature_list)
    server.register_method("experimentalFeature/enablement/set", _experimental_feature_enablement_set)
