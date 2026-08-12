"""Shared user-input resolver bridging ask_user_confirm_card to the desktop
(issue #646).

The KUN runtime wires its own UserInputGate via the AgentLoop. The legacy
runtime (chat.send path, which the desktop currently uses) executes tools
through ToolRuntime/ToolOrchestrator without a gate. This module provides a
shared gate + injectable emitter so the legacy path can also block on a user
choice and emit user_input_requested events toward the desktop.

Wiring:
  bridge/loop.py (chat.send):
      set_user_input_emitter(lambda payload: asyncio.create_task(_emit("user_input_requested", payload)))
      app_server.register_method("userInput.resolve", user_input_resolve_handler)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from miqi.kun_runtime.user_input_gate import UserInputGate

_gate = UserInputGate()
_emitter: Callable[[dict[str, Any]], Any] | None = None


def set_user_input_emitter(emitter: Callable[[dict[str, Any]], Any] | None) -> None:
    """Set the event emitter used to push user_input_requested to the desktop.

    The bridge sets this per chat.send session. When None (headless),
    resolve() returns a cancelled result instead of blocking forever.
    """
    global _emitter
    _emitter = emitter


def user_input_emitter() -> Callable[[dict[str, Any]], Any] | None:
    return _emitter


def resolve_user_input(
    input_id: str,
    answers: dict[str, Any] | None = None,
) -> bool:
    """Resolve a pending user-input request (called by the app handler)."""
    return _gate.resolve(input_id, answers or {})


def make_resolver() -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build the async resolver injected into AskUserConfirmCardTool.

    Blocks on the shared gate until the desktop resolves, times out, or the
    turn is cancelled. Emits user_input_requested so the desktop renders the
    confirm card.
    """

    async def resolver(payload: dict[str, Any]) -> dict[str, Any]:
        emitter = _emitter
        if emitter is None:
            return {
                "status": "cancelled",
                "reason": "no user-input channel (desktop bridge not wired)",
            }
        input_id = f"user_input_{__import__('uuid').uuid4().hex[:12]}"
        prompt = str(payload.get("message") or payload.get("title") or "")
        try:
            if asyncio.iscoroutinefunction(emitter):
                await emitter({**payload, "input_id": input_id, "prompt": prompt})
            else:
                emitter({**payload, "input_id": input_id, "prompt": prompt})
        except Exception:
            pass  # emitter failure must not block the tool; timeout will cancel
        timeout = payload.get("timeout_seconds")
        result = await _gate.request(
            thread_id=str(payload.get("threadId") or ""),
            turn_id=str(payload.get("turnId") or ""),
            item_id=f"item_{input_id[-6:]}",
            prompt=prompt,
            timeout=float(timeout) if timeout else None,
            input_id=input_id,
        )
        result["request_id"] = input_id
        return result

    return resolver


def resolver_to_tool_result(gate_result: dict[str, Any]) -> str:
    """Convert a gate result into the ask_user_confirm_card tool-result JSON."""
    from miqi.agent.tools.ask_user_confirm import AskUserConfirmCardTool

    return AskUserConfirmCardTool.build_result(gate_result)


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)
