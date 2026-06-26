"""Per-thread usage accumulation service.

Aligns with KUN ``services/usage-service.ts``.
"""

from __future__ import annotations

from typing import Any


class UsageService:
    """Accumulates usage (tokens, cost) per thread."""

    def __init__(self) -> None:
        # threadId → accumulated snapshot
        self._snapshots: dict[str, dict[str, Any]] = {}

    def record(self, thread_id: str, usage: dict[str, Any]) -> dict[str, Any]:
        """Record a single usage delta and return the accumulated snapshot.

        *usage* is a dict matching ``UsageSnapshot`` fields (promptTokens,
        completionTokens, totalTokens, costUsd, etc.).
        """
        current = self._snapshots.get(thread_id, {})
        acc = _merge_usage(current, usage)
        self._snapshots[thread_id] = acc
        return acc

    def record_token_economy_savings(self, thread_id: str, savings: dict[str, Any]) -> dict[str, Any]:
        """Record token-economy savings without changing prompt/completion/total tokens."""
        current = self._snapshots.get(thread_id, {})
        acc = {**current}
        for key in ("tokenEconomySavingsTokens", "tokenEconomySavingsUsd", "tokenEconomySavingsCny"):
            val = savings.get(key)
            if isinstance(val, (int, float)):
                acc[key] = acc.get(key, 0) + val
        self._snapshots[thread_id] = acc
        return acc

    def for_thread(self, thread_id: str) -> dict[str, Any]:
        """Return the accumulated usage snapshot for *thread_id* (never None)."""
        return self._snapshots.get(thread_id, {})

    def seed_thread(self, thread_id: str, snapshot: dict[str, Any]) -> None:
        """Pre-populate usage for an existing thread (e.g. on server restart)."""
        self._snapshots[thread_id] = dict(snapshot)

    def reset(self, thread_id: str) -> None:
        self._snapshots.pop(thread_id, None)


def _merge_usage(current: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Accumulate numeric usage fields.  Non-numeric fields are overwritten."""
    acc = dict(current)
    for key, value in delta.items():
        if isinstance(value, (int, float)):
            acc[key] = acc.get(key, 0) + value
        else:
            acc[key] = value
    return acc
