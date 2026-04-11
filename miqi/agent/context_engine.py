"""Pluggable context engine abstract base class.

Inspired by Hermes Agent's agent/context_engine.py.
Provides the interface that ContextCompressor implements.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ContextEngine(ABC):
    """Abstract base class for pluggable context compression engines.

    A ContextEngine is responsible for reducing the size of the conversation
    history when it grows too large, while preserving the most important
    information.
    """

    @abstractmethod
    async def compress(
        self,
        messages: list[dict[str, Any]],
        model: str,
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        """Compress the conversation history.

        Args:
            messages: Full conversation messages (may include system prompt at index 0).
            model: The model identifier used for summary generation.
            session_id: Optional session ID for logging/lineage tracking.

        Returns:
            Compressed message list. Must preserve the system prompt (index 0)
            and end with a user message.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine name for logging."""
