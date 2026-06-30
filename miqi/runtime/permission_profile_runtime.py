"""Permission profile catalog — built-in profiles and paginated listing.

Does not change active runtime behavior. Profiles are returned
deterministically sorted by id.
"""

from __future__ import annotations

from typing import Any

BUILTIN_PERMISSION_PROFILES: dict[str, dict[str, Any]] = {
    ":read-only": {
        "description": "Read files and inspect state, but do not mutate files or run commands.",
        "filesystem_mode": "workspace-readonly",
        "network": "none",
        "allow_exec": False,
        "network_allowed": False,
    },
    ":workspace": {
        "description": "Read and write inside the workspace with restricted network.",
        "filesystem_mode": "workspace-write",
        "network": "restricted",
        "allow_exec": True,
        "network_allowed": False,
    },
    ":full-access": {
        "description": "Allow broad execution and network access after approval policy.",
        "filesystem_mode": "restricted",
        "network": "allowed",
        "allow_exec": True,
        "network_allowed": True,
    },
}


class PermissionProfileRuntime:
    """Catalog of available permission profiles.

    Returns built-in profiles plus any config-defined profiles.
    """

    def __init__(self) -> None:
        self._config_profiles: dict[str, dict[str, Any]] = {}

    def list_profiles(
        self, cwd: str | None = None, cursor: str | None = None, limit: int = 100,
    ) -> dict[str, Any]:
        """Return a page of profiles sorted by id.

        Returns:
            {"data": [...], "nextCursor": str|None}
        """
        # Merge builtins + config-defined; config overrides builtins
        merged: dict[str, dict[str, Any]] = {}
        for pid, meta in BUILTIN_PERMISSION_PROFILES.items():
            merged[pid] = {"source": "builtin", **meta}
        for pid, meta in self._config_profiles.items():
            merged[pid] = {"source": "config", **meta}

        all_ids = sorted(merged.keys())
        start = 0
        if cursor is not None:
            try:
                start = all_ids.index(cursor) + 1
            except ValueError:
                start = len(all_ids)

        page_ids = all_ids[start : start + limit]
        data: list[dict[str, Any]] = []
        for pid in page_ids:
            meta = merged[pid]
            data.append({
                "id": pid,
                "description": meta.get("description", ""),
                "source": meta.get("source", "builtin"),
                "filesystemMode": meta.get("filesystem_mode", "workspace-write"),
                "network": meta.get("network", "restricted"),
                "allowExec": meta.get("allow_exec", True),
                "networkAllowed": meta.get("network_allowed", False),
            })

        next_cursor = page_ids[-1] if page_ids and start + limit < len(all_ids) else None
        return {"data": data, "nextCursor": next_cursor}
