"""MiQi runtime — multi-agent execution engine."""

from __future__ import annotations

from typing import Any

__all__ = ["RuntimeClient", "RuntimeSession"]


def __getattr__(name: str) -> Any:
    if name == "RuntimeClient":
        from miqi.runtime.client import RuntimeClient

        return RuntimeClient
    if name == "RuntimeSession":
        from miqi.runtime.session import RuntimeSession

        return RuntimeSession
    raise AttributeError(name)
