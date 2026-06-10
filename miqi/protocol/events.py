"""Typed event protocol for MiQi runtime.

All events are immutable dataclasses serializable to JSON.
The protocol uses a Submission-Queue / Event-Queue pattern:
  - Frontend pushes Submissions (user messages, approvals, config changes)
  - Runtime emits Events (streaming text, tool progress, state changes)
"""

from __future__ import annotations
