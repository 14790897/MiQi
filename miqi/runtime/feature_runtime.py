"""Process-local experimental feature catalog and enablement overrides.

Maps experimental feature keys to stage metadata and a per-process
enablement dictionary. Invalid keys are silently ignored on set.
"""

from __future__ import annotations

from typing import Any

DEFAULT_FEATURES: dict[str, dict[str, Any]] = {
    "runtime.session": {
        "stage": "stable",
        "default_enabled": True,
        "displayName": "Runtime Sessions",
        "description": "Persistent per-client runtime sessions with isolated state.",
    },
    "runtime.ledger": {
        "stage": "stable",
        "default_enabled": True,
        "displayName": "Runtime Ledger",
        "description": "Durable event ledger recording all tool calls and turn completions.",
    },
    "runtime.replay": {
        "stage": "stable",
        "default_enabled": True,
        "displayName": "Runtime Replay",
        "description": "Deterministic replay of completed turns from the event ledger.",
    },
    "runtime.appServer": {
        "stage": "stable",
        "default_enabled": True,
        "displayName": "App Server",
        "description": "Codex-style JSON-RPC app server bridge.",
    },
    "runtime.mcpStatus": {
        "stage": "beta",
        "default_enabled": True,
        "displayName": "MCP Status",
        "description": "Live MCP server status monitoring and resource inspection.",
    },
    "runtime.codexThreads": {
        "stage": "beta",
        "default_enabled": True,
        "displayName": "Codex Threads",
        "description": "Codex-style thread management: fork, rollback, notifications.",
    },
    "runtime.sandboxDepth": {
        "stage": "beta",
        "default_enabled": True,
        "displayName": "Sandbox Depth",
        "description": "Per-turn sandbox depth configuration for tool execution.",
    },
    "desktop.next": {
        "stage": "underDevelopment",
        "default_enabled": False,
        "displayName": "Desktop Next",
        "description": "Next-generation Desktop UI (preview).",
    },
}


class FeatureRuntime:
    """Process-local experimental feature state.

    Each feature has a fixed catalog entry (stage, default), plus an
    optional process-local override stored in ``_enablement``.
    """

    def __init__(self) -> None:
        self._enablement: dict[str, bool] = {}

    # ── query ──────────────────────────────────────────────────────────

    def list_features(self, cursor: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Return a page of features sorted by key.

        Returns:
            {"data": [...], "nextCursor": str|None}
        """
        all_keys = sorted(DEFAULT_FEATURES.keys())
        start = 0
        if cursor is not None:
            try:
                start = all_keys.index(cursor) + 1
            except ValueError:
                start = len(all_keys)

        page_keys = all_keys[start : start + limit]
        data: list[dict[str, Any]] = []
        for key in page_keys:
            meta = DEFAULT_FEATURES[key]
            enabled = self._enablement.get(key, meta["default_enabled"])
            data.append({
                "key": key,
                "stage": meta["stage"],
                "enabled": enabled,
                "defaultEnabled": meta["default_enabled"],
                "displayName": meta.get("displayName"),
                "description": meta.get("description"),
            })
        next_cursor = all_keys[start + limit] if start + limit < len(all_keys) else None
        return {"data": data, "nextCursor": next_cursor}

    def is_enabled(self, key: str) -> bool:
        meta = DEFAULT_FEATURES.get(key)
        if meta is None:
            return False
        if key in self._enablement:
            return self._enablement[key]
        return bool(meta["default_enabled"])

    # ── mutation ───────────────────────────────────────────────────────

    def set_enablement(self, features: dict[str, bool]) -> list[str]:
        """Apply enablement overrides for known keys. Invalid keys are ignored.

        Returns the list of ignored (invalid) keys.
        """
        ignored: list[str] = []
        for key, value in features.items():
            if key not in DEFAULT_FEATURES:
                ignored.append(key)
                continue
            self._enablement[key] = bool(value)
        return ignored
