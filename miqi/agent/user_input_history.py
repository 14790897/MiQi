"""User-confirmation decision history (issue #646, 功能描述⑤).

Records every ask_user_confirm_card decision — call time, card title, and the
user's final choice — for audit. Mirrors the approval-history pattern in
``miqi/agent/command_approval.py``: in-memory ring + optional JSONL file.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

logger = None  # lazy import to avoid loguru at module import

_lock = threading.Lock()
_history: list[dict[str, Any]] = []
_history_file: str | None = None


def init_history_file(path: str) -> None:
    """Load existing entries from *path* and append new ones to it."""
    global _history_file
    _history_file = path
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    _history.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass


def add_user_input_history(
    *,
    title: str,
    message: str = "",
    choices: list[dict[str, Any]] | None = None,
    status: str = "submitted",  # submitted | cancelled
    choice_id: str = "",
    choice_label: str = "",
    reason: str = "",  # e.g. timeout / turn_stop / user_cancel
    thread_id: str = "",
    turn_id: str = "",
    input_id: str = "",
) -> dict[str, Any]:
    """Record one user-confirmation decision."""
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "input_id": input_id,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "title": title,
        "message": message,
        "choices": choices or [],
        "status": status,
        "choice_id": choice_id,
        "choice_label": choice_label,
        "reason": reason,
    }
    with _lock:
        _history.append(entry)
        if _history_file:
            try:
                with open(_history_file, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                pass
    return entry


def get_user_input_history(limit: int = 200) -> list[dict[str, Any]]:
    """Return recent decisions (most recent first)."""
    with _lock:
        return list(reversed(_history[-limit:]))


def clear_history() -> None:
    """Clear in-memory history (used by tests)."""
    with _lock:
        _history.clear()
