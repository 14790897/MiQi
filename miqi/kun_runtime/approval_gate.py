"""Approval gate for KUN runtime — pause execution until user approves or denies.

Aligns with KUN ``ports/approval-gate.ts`` and ``adapters/in-memory-approval-gate.ts``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal


class ApprovalRequest:
    """An approval request waiting for a decision."""

    def __init__(
        self,
        approval_id: str,
        thread_id: str,
        turn_id: str,
        tool_name: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ):
        self.id = approval_id
        self.thread_id = thread_id
        self.turn_id = turn_id
        self.tool_name = tool_name
        self.summary = summary
        self.details = details or {}
        self._event = asyncio.Event()
        self._decision: Literal["allow", "deny"] | None = None

    @property
    def resolved(self) -> bool:
        return self._decision is not None

    @property
    def decision(self) -> Literal["allow", "deny"] | None:
        return self._decision

    def resolve(self, decision: Literal["allow", "deny"]) -> None:
        if self._decision is not None:
            return  # already resolved
        self._decision = decision
        self._event.set()

    def cancel(self) -> None:
        if self._decision is not None:
            return
        self._decision = "deny"
        self._event.set()

    async def wait(self, timeout: float | None = None) -> Literal["allow", "deny"]:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._decision = "deny"
        return self._decision or "deny"


class ApprovalGate:
    """Manages approval requests for tool calls requiring user confirmation."""

    def __init__(self, approval_bypass: Any | None = None) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self.approval_bypass = approval_bypass

    async def request(
        self,
        thread_id: str,
        turn_id: str,
        tool_name: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> Literal["allow", "deny"]:
        """Submit an approval request and wait for the decision."""
        if self._bypasses_tool_confirmation():
            return "allow"
        approval_id = f"approval_{uuid.uuid4().hex[:12]}"
        req = ApprovalRequest(
            approval_id=approval_id,
            thread_id=thread_id,
            turn_id=turn_id,
            tool_name=tool_name,
            summary=summary,
            details=details,
        )
        self._pending[approval_id] = req
        try:
            return await req.wait()
        finally:
            self._pending.pop(approval_id, None)

    def resolve(self, approval_id: str, decision: Literal["allow", "deny"]) -> bool:
        """Resolve a pending approval. Returns True if the approval existed."""
        req = self._pending.get(approval_id)
        if req is None:
            return False
        req.resolve(decision)
        return True

    def cancel_all(self, turn_id: str) -> None:
        """Cancel all pending approvals for a turn (e.g. on interrupt)."""
        for req in list(self._pending.values()):
            if req.turn_id == turn_id:
                req.cancel()
                self._pending.pop(req.id, None)

    def get_pending(self, turn_id: str | None = None) -> list[ApprovalRequest]:
        """Return pending approvals, optionally filtered by turn."""
        if turn_id is None:
            return list(self._pending.values())
        return [r for r in self._pending.values() if r.turn_id == turn_id]

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def _bypasses_tool_confirmation(self) -> bool:
        bypass = self.approval_bypass
        if bypass is None:
            return False
        bypasses_category = getattr(bypass, "bypasses_category", None)
        if callable(bypasses_category):
            return bool(bypasses_category("tool"))
        return bool(
            getattr(bypass, "bypass_all", False)
            or getattr(bypass, "bypass_tool_confirmation", False)
        )
