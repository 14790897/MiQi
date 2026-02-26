"""Memory package for the FeatherFlow agent.

Re-exports :class:`MemoryStore` for backward compatibility so that
``from featherflow.agent.memory import MemoryStore`` keeps working.
"""

from featherflow.agent.memory.store import MemoryStore

__all__ = ["MemoryStore"]
