"""Permission profile — per-turn sandbox and permission configuration.

Attached to TurnContext so the orchestrator can consult it when
making permission and sandbox decisions for each tool call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PermissionProfile:
    """Per-turn permission and sandbox policy.

    Attached to TurnContext before each turn. The orchestrator reads
    this profile to make permission decisions and configure sandbox
    isolation levels.
    """

    workspace: Path
    filesystem_mode: str = "workspace-write"  # workspace-write | workspace-readonly | restricted
    network: str = "restricted"  # restricted | allowed | none
    allow_exec: bool = True
    permanent_allowlist: set[str] = field(default_factory=set)
