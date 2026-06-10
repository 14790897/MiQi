"""Typed event protocol for MiQi runtime.

All events are immutable dataclasses serializable to JSON.
The protocol uses a Submission-Queue / Event-Queue pattern:
  - Frontend pushes Submissions (user messages, approvals, config changes)
  - Runtime emits Events (streaming text, tool progress, state changes)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time


# ── Event Severity ──────────────────────────────────────────

class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ── Agent Status ────────────────────────────────────────────

class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    ERROR = "error"
    ABORTED = "aborted"
