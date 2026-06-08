"""Phase 7 tests — ApprovalGate and UserInputGate."""

from __future__ import annotations

import asyncio

import pytest

from miqi.kun_runtime.approval_gate import ApprovalGate, ApprovalRequest
from miqi.kun_runtime.user_input_gate import UserInputGate, UserInputRequest


# ═══════════════════════════════════════════════════════════════════════════════
# ApprovalGate tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestApprovalRequest:
    def test_initial_pending(self) -> None:
        req = ApprovalRequest("id1", "th1", "t1", "bash", "rm -rf /")
        assert not req.resolved
        assert req.decision is None

    def test_resolve_allow(self) -> None:
        req = ApprovalRequest("id1", "th1", "t1", "bash", "rm -rf /")
        req.resolve("allow")
        assert req.resolved
        assert req.decision == "allow"

    def test_resolve_deny(self) -> None:
        req = ApprovalRequest("id1", "th1", "t1", "bash", "rm -rf /")
        req.resolve("deny")
        assert req.resolved
        assert req.decision == "deny"

    def test_double_resolve_idempotent(self) -> None:
        req = ApprovalRequest("id1", "th1", "t1", "bash", "danger")
        req.resolve("allow")
        req.resolve("deny")  # should be ignored
        assert req.decision == "allow"

    def test_cancel(self) -> None:
        req = ApprovalRequest("id1", "th1", "t1", "bash", "danger")
        req.cancel()
        assert req.resolved
        assert req.decision == "deny"

    @pytest.mark.asyncio
    async def test_wait_resolved(self) -> None:
        req = ApprovalRequest("id1", "th1", "t1", "bash", "danger")

        async def resolver() -> None:
            await asyncio.sleep(0.05)
            req.resolve("allow")

        asyncio.create_task(resolver())
        decision = await asyncio.wait_for(req.wait(), timeout=1.0)
        assert decision == "allow"

    @pytest.mark.asyncio
    async def test_wait_timeout_denies(self) -> None:
        req = ApprovalRequest("id1", "th1", "t1", "bash", "danger")
        decision = await req.wait(timeout=0.01)
        assert decision == "deny"


class TestApprovalGate:
    @pytest.mark.asyncio
    async def test_request_and_resolve_allow(self) -> None:
        gate = ApprovalGate()
        # Start request in background
        async def do_request() -> str:
            return await gate.request("th1", "t1", "bash", "rm -rf /")
        task = asyncio.create_task(do_request())
        await asyncio.sleep(0.05)

        # Resolve
        pending = gate.get_pending("t1")
        assert len(pending) == 1
        assert gate.resolve(pending[0].id, "allow") is True

        result = await asyncio.wait_for(task, timeout=1.0)
        assert result == "allow"
        assert gate.pending_count == 0

    @pytest.mark.asyncio
    async def test_request_and_resolve_deny(self) -> None:
        gate = ApprovalGate()
        task = asyncio.create_task(gate.request("th1", "t1", "bash", "rm -rf /"))
        await asyncio.sleep(0.05)

        pending = gate.get_pending()
        gate.resolve(pending[0].id, "deny")

        result = await asyncio.wait_for(task, timeout=1.0)
        assert result == "deny"

    @pytest.mark.asyncio
    async def test_cancel_all_for_turn(self) -> None:
        gate = ApprovalGate()
        task1 = asyncio.create_task(gate.request("th1", "t1", "bash", "cmd1"))
        task2 = asyncio.create_task(gate.request("th1", "t2", "bash", "cmd2"))
        await asyncio.sleep(0.05)

        gate.cancel_all("t1")
        r1 = await asyncio.wait_for(task1, timeout=1.0)
        assert r1 == "deny"

        # t2 should still be pending
        assert gate.pending_count == 1
        pending = gate.get_pending("t2")
        assert len(pending) == 1
        gate.resolve(pending[0].id, "allow")
        r2 = await asyncio.wait_for(task2, timeout=1.0)
        assert r2 == "allow"

    @pytest.mark.asyncio
    async def test_resolve_nonexistent(self) -> None:
        gate = ApprovalGate()
        assert gate.resolve("nonexistent", "allow") is False

    def test_filter_by_turn(self) -> None:
        gate = ApprovalGate()
        # We can't easily test filtering without async context,
        # but the method itself doesn't do IO
        assert gate.get_pending("t1") == []
        assert gate.get_pending() == []

    def test_pending_count(self) -> None:
        gate = ApprovalGate()
        assert gate.pending_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# UserInputGate tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUserInputRequest:
    def test_initial_pending(self) -> None:
        req = UserInputRequest("in1", "th1", "t1", "item1", "Which file?")
        assert not req.resolved
        assert req.resolution is None

    def test_resolve_with_answers(self) -> None:
        req = UserInputRequest("in1", "th1", "t1", "item1", "Which file?")
        req.resolve({"q1": "yes"})
        assert req.resolved
        assert req.resolution is not None
        assert req.resolution["status"] == "submitted"
        assert req.resolution["answers"] == {"q1": "yes"}

    def test_cancel(self) -> None:
        req = UserInputRequest("in1", "th1", "t1", "item1", "Which file?")
        req.cancel()
        assert req.resolved
        assert req.resolution == {"status": "cancelled"}

    @pytest.mark.asyncio
    async def test_wait_timeout_cancels(self) -> None:
        req = UserInputRequest("in1", "th1", "t1", "item1", "Prompt")
        resolution = await req.wait(timeout=0.01)
        assert resolution["status"] == "cancelled"


class TestUserInputGate:
    @pytest.mark.asyncio
    async def test_request_and_resolve(self) -> None:
        gate = UserInputGate()
        task = asyncio.create_task(
            gate.request("th1", "t1", "item1", "Which file?", [
                {"header": "Choice", "id": "q1", "question": "Pick one", "options": []},
            ])
        )
        await asyncio.sleep(0.05)

        pending = gate.get_pending("t1")
        assert len(pending) == 1
        assert gate.resolve(pending[0].id, {"q1": "a.txt"}) is True

        result = await asyncio.wait_for(task, timeout=1.0)
        assert result["status"] == "submitted"
        assert result["answers"] == {"q1": "a.txt"}

    @pytest.mark.asyncio
    async def test_cancel_all_for_turn(self) -> None:
        gate = UserInputGate()
        task = asyncio.create_task(
            gate.request("th1", "t1", "item1", "Prompt?")
        )
        await asyncio.sleep(0.05)

        gate.cancel_all("t1")
        result = await asyncio.wait_for(task, timeout=1.0)
        assert result["status"] == "cancelled"
        assert gate.pending_count == 0

    @pytest.mark.asyncio
    async def test_resolve_nonexistent(self) -> None:
        gate = UserInputGate()
        assert gate.resolve("nonexistent") is False

    def test_pending_count(self) -> None:
        gate = UserInputGate()
        assert gate.pending_count == 0
