"""Session state — mutable runtime state for one RuntimeSession.

Holds session identity, workspace, active thread, and a snapshot of
the runtime config. Owned by RuntimeServices; shared across
TaskRunner, TurnRunner, and other runtime components.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SessionState:
    """Mutable runtime state for one RuntimeSession.

    Supports runtime config mutation via apply_config_update(),
    which navigates dot-separated paths on config_snapshot.
    """

    session_id: str
    workspace: Path
    active_thread_id: str
    config_snapshot: Any

    def apply_config_update(self, path: str, value: Any) -> None:
        """Apply a runtime config update by navigating dot-separated path.

        E.g., path="agents.defaults.temperature" sets
        self.config_snapshot.agents.defaults.temperature = value.

        Raises ValueError for paths containing dunder/private segments.
        """
        target: Any = self.config_snapshot
        parts = path.split(".")
        for part in parts:
            if "__" in part or part.startswith("_"):
                raise ValueError(
                    f"Invalid config path segment {part!r}: "
                    f"dunder and private attributes are not allowed"
                )
        for part in parts[:-1]:
            target = getattr(target, part)
        setattr(target, parts[-1], value)
