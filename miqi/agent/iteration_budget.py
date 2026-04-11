"""Iteration budget system, ported from Hermes Agent's run_agent.py.

IterationBudget is a thread-safe counter that tracks how many iterations the
agent has consumed.  When the budget is 70% or 90% exhausted, warning messages
are injected into the last tool result so the model naturally adjusts behaviour.

Constants match Hermes verbatim:
    default max_iterations  = 90
    subagent max_iterations = 50
    caution threshold       = 0.70  (70% used  → "Start consolidating")
    warning threshold       = 0.90  (90% used  → "Provide final response NOW")
    injected key            = "_budget_warning"   (inside last tool result JSON)
"""
from __future__ import annotations

import asyncio
from typing import Any


class IterationBudget:
    """Thread-safe iteration counter with two-level pressure warnings.

    Usage::

        budget = IterationBudget(max_iterations=90)
        while not budget.exhausted:
            budget.consume()          # raises StopIteration when exhausted
            ...
        # After each tool result is built, optionally inject warning:
        result_json = budget.maybe_inject_warning(result_json)
    """

    _caution_threshold = 0.70   # 70%  → caution message
    _warning_threshold = 0.90   # 90%  → urgent warning

    _CAUTION_MSG = (
        "Note: You have used {pct:.0f}% of your iteration budget "
        "({used}/{max} steps). Start consolidating your work and preparing "
        "a summary response. Avoid starting new large tasks."
    )
    _WARNING_MSG = (
        "URGENT: You have used {pct:.0f}% of your iteration budget "
        "({used}/{max} steps). Provide your final response NOW. "
        "Do not call more tools unless absolutely required to answer."
    )

    def __init__(self, max_iterations: int = 90):
        self._max = max(1, max_iterations)
        self._used = 0
        self._lock = asyncio.Lock()

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def max_iterations(self) -> int:
        return self._max

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self._max - self._used)

    @property
    def exhausted(self) -> bool:
        return self._used >= self._max

    @property
    def fraction_used(self) -> float:
        return self._used / self._max

    # ── Mutation ────────────────────────────────────────────────────────────

    def consume(self) -> None:
        """Increment the counter. Raises StopIteration when budget exhausted."""
        self._used += 1
        if self._used > self._max:
            raise StopIteration(f"Iteration budget exhausted ({self._max} steps)")

    def refund(self, n: int = 1) -> None:
        """Refund N iterations (used when execute_code iterations are returned)."""
        self._used = max(0, self._used - n)

    async def consume_async(self) -> None:
        """Async version of consume (lock-protected for coroutine safety)."""
        async with self._lock:
            self.consume()

    # ── Warning injection ───────────────────────────────────────────────────

    def maybe_inject_warning(self, tool_result: Any) -> Any:
        """Inject a budget-pressure warning into a tool result dict if thresholds are crossed.

        The warning is added as ``_budget_warning`` key so the model reads it
        as part of the tool response (matches Hermes behaviour exactly).

        Args:
            tool_result: The tool result — either a dict or a str that may be valid JSON.

        Returns:
            Modified tool_result with warning injected, or unchanged if no warning needed.
        """
        frac = self.fraction_used
        if frac < self._caution_threshold:
            return tool_result

        pct = frac * 100
        if frac >= self._warning_threshold:
            msg = self._WARNING_MSG.format(pct=pct, used=self._used, max=self._max)
        else:
            msg = self._CAUTION_MSG.format(pct=pct, used=self._used, max=self._max)

        # Inject into dict results directly
        if isinstance(tool_result, dict):
            result = dict(tool_result)
            result["_budget_warning"] = msg
            return result

        # Try to inject into JSON-string results
        if isinstance(tool_result, str):
            import json
            try:
                parsed = json.loads(tool_result)
                if isinstance(parsed, dict):
                    parsed["_budget_warning"] = msg
                    return json.dumps(parsed, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                # Not a JSON object — append as plain text
                return tool_result + f"\n\n{msg}"

        return tool_result

    def __repr__(self) -> str:
        return (
            f"IterationBudget(used={self._used}, max={self._max}, "
            f"remaining={self.remaining}, {self.fraction_used:.0%})"
        )
