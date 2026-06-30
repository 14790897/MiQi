"""Thread-level orchestration and lifecycle management.

ThreadManager owns the relationship between threads and agents.
It provides the bridge between the old session-based model and
the new multi-agent thread model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThreadState:
    """Runtime state for a single thread."""
    thread_id: str
    agent_id: str | None = None
    is_active: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ThreadManager:
    """Manages thread → agent mapping and lifecycle.

    During Phase 2 migration, this wraps the existing SessionManager
    and adds the agent mapping layer. The SessionManager continues
    to handle persistence.
    """

    def __init__(self):
        self._threads: dict[str, ThreadState] = {}

    def get_or_create(self, thread_id: str) -> ThreadState:
        if thread_id not in self._threads:
            self._threads[thread_id] = ThreadState(thread_id=thread_id)
        return self._threads[thread_id]

    def bind_agent(self, thread_id: str, agent_id: str) -> None:
        thread = self.get_or_create(thread_id)
        thread.agent_id = agent_id
        thread.is_active = True

    def unbind_agent(self, thread_id: str) -> None:
        thread = self.get_or_create(thread_id)
        thread.agent_id = None
        thread.is_active = False

    def list_active(self) -> list[ThreadState]:
        return [t for t in self._threads.values() if t.is_active]

    def get(self, thread_id: str) -> ThreadState | None:
        return self._threads.get(thread_id)
