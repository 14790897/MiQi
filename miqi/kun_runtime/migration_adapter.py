"""Bridge between MiQi legacy session model and KUN thread model.

Provides the ``session_key → threadId`` mapping so new KUN threads can
coexist with old MiQi sessions without data migration.
"""

from __future__ import annotations

# Simple in-memory bidirectional mapping.
# In production this could be backed by a JSON file or SQLite metadata table.
_SESSION_TO_THREAD: dict[str, str] = {}
_THREAD_TO_SESSION: dict[str, str] = {}


def session_key_to_thread_id(session_key: str) -> str:
    """Map a MiQi session key (``channel:chat_id``) to a KUN thread ID.

    If no mapping exists yet, a new thread ID is generated.
    Generates deterministic thread IDs based on session key for idempotency.
    """
    if session_key in _SESSION_TO_THREAD:
        return _SESSION_TO_THREAD[session_key]
    # Deterministic: use a stable hash so restarts produce the same mapping
    thread_id = _make_thread_id(session_key)
    _SESSION_TO_THREAD[session_key] = thread_id
    _THREAD_TO_SESSION[thread_id] = session_key
    return thread_id


def thread_id_to_session_key(thread_id: str) -> str | None:
    """Reverse mapping: return the MiQi session key for a KUN thread ID."""
    return _THREAD_TO_SESSION.get(thread_id)


def register_mapping(session_key: str, thread_id: str) -> None:
    """Explicitly register a mapping (e.g. when loading from persistence)."""
    _SESSION_TO_THREAD[session_key] = thread_id
    _THREAD_TO_SESSION[thread_id] = session_key


def clear_mapping(session_key: str) -> None:
    """Remove a mapping (e.g. when a thread is deleted)."""
    thread_id = _SESSION_TO_THREAD.pop(session_key, None)
    if thread_id:
        _THREAD_TO_SESSION.pop(thread_id, None)


def _make_thread_id(session_key: str) -> str:
    """Generate a stable, URL-safe thread ID from a session key."""
    import hashlib
    h = hashlib.sha256(session_key.encode()).hexdigest()
    return f"thread_{h[:16]}"
