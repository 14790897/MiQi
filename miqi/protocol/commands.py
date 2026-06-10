"""Submission/Command types — messages from frontend → runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import time


@dataclass
class UserMessage:
    """A user chat message."""
    type: str = field(default="user_message", init=False)
    content: str
    thread_id: str | None = None  # None = use active thread
    media: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ApprovalResponse:
    """User response to an approval request."""
    type: str = field(default="approval_response", init=False)
    approval_id: str
    decision: str  # "allow" | "deny" | "allow_permanent"


@dataclass
class AbortTurn:
    """User requests to abort the current turn."""
    type: str = field(default="abort_turn", init=False)
    thread_id: str | None = None


@dataclass
class ConfigUpdate:
    """Configuration was changed through the UI."""
    type: str = field(default="config_update", init=False)
    path: str  # dot-separated config path, e.g. "permissions.filesystem"
    value: Any


@dataclass
class ThreadCommand:
    """Thread lifecycle commands."""
    type: str = field(default="thread_command", init=False)
    action: str  # "new" | "archive" | "delete" | "fork" | "rename"
    thread_id: str
    params: dict[str, Any] = field(default_factory=dict)


# ── Union type ──────────────────────────────────────────────

Submission = UserMessage | ApprovalResponse | AbortTurn | ConfigUpdate | ThreadCommand
