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
    """Mutable runtime state for one RuntimeSession."""

    session_id: str
    workspace: Path
    active_thread_id: str
    config_snapshot: Any
