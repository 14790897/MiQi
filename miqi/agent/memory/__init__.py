"""Memory package for the MiQi agent.

Re-exports :class:`MemoryStore` for backward compatibility so that
``from miqi.agent.memory import MemoryStore`` keeps working.
"""

from miqi.agent.memory.store import MemoryStore

__all__ = ["MemoryStore"]
