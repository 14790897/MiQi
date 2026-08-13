"""User input gate for KUN runtime — pause execution for interactive questions.

Aligns with KUN ``ports/user-input-gate.ts`` and ``adapters/in-memory-user-input-gate.ts``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any


class UserInputRequest:
    """A request for user input (e.g. clarifying questions)."""

    def __init__(
        self,
        input_id: str,
        thread_id: str,
        turn_id: str,
        item_id: str,
        prompt: str,
        questions: list[dict[str, Any]] | None = None,
    ):
        self.id = input_id
        self.thread_id = thread_id
        self.turn_id = turn_id
        self.item_id = item_id
        self.prompt = prompt
        self.questions = questions or []
        self._event = asyncio.Event()
        self._resolution: dict[str, Any] | None = None

    @property
    def resolved(self) -> bool:
        return self._resolution is not None

    @property
    def resolution(self) -> dict[str, Any] | None:
        return self._resolution

    def resolve(self, answers: dict[str, str] | None = None) -> None:
        if self._resolution is not None:
            return
        self._resolution = {
            "status": "submitted",
            "answers": answers or {},
        }
        self._event.set()

    def cancel(self) -> None:
        if self._resolution is not None:
            return
        self._resolution = {"status": "cancelled"}
        self._event.set()

    async def wait(self, timeout: float | None = None) -> dict[str, Any]:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._resolution = {"status": "cancelled"}
        return self._resolution or {"status": "cancelled"}


class UserInputGate:
    """Manages interactive user input requests during agent execution."""

    def __init__(self) -> None:
        self._pending: dict[str, UserInputRequest] = {}

    async def request(
        self,
        thread_id: str,
        turn_id: str,
        item_id: str,
        prompt: str,
        questions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Submit a user input request and wait for resolution."""
        input_id = f"user_input_{uuid.uuid4().hex[:12]}"
        req = UserInputRequest(
            input_id=input_id,
            thread_id=thread_id,
            turn_id=turn_id,
            item_id=item_id,
            prompt=prompt,
            questions=questions,
        )
        self._pending[input_id] = req
        try:
            return await req.wait()
        finally:
            self._pending.pop(input_id, None)

    def resolve(self, input_id: str, answers: dict[str, str] | None = None) -> bool:
        """Resolve a pending user input request. Returns True if it existed."""
        req = self._pending.get(input_id)
        if req is None:
            return False
        req.resolve(answers)
        return True

    def cancel_all(self, turn_id: str) -> None:
        """Cancel all pending input requests for a turn."""
        for req in list(self._pending.values()):
            if req.turn_id == turn_id:
                req.cancel()
                self._pending.pop(req.id, None)

    def get_pending(self, turn_id: str | None = None) -> list[UserInputRequest]:
        """Return pending input requests, optionally filtered by turn."""
        if turn_id is None:
            return list(self._pending.values())
        return [r for r in self._pending.values() if r.turn_id == turn_id]

    @property
    def pending_count(self) -> int:
        return len(self._pending)
