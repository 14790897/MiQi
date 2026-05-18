"""MemoryProvider Protocol — extensibility point for external memory sources."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MemoryProvider(Protocol):
    """Protocol for pluggable memory providers.

    Registered providers contribute a system-prompt block to every
    get_memory_context() call and receive per-turn sync calls.
    """

    @property
    def name(self) -> str: ...

    def system_prompt_block(self, session_key: str, current_message: str) -> str: ...

    def sync_turn(self, session_key: str, user_msg: str, assistant_msg: str) -> None: ...

    def on_session_end(self, session_key: str) -> None: ...

    def flush(self) -> None: ...
