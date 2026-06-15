"""Codex-style turn AppServer handlers.

Registers turn/start, turn/interrupt, turn/steer, thread/compact/start,
and thread/inject_items.  All handlers flow through RuntimeSession.
"""

from __future__ import annotations

import uuid
from typing import Any

from miqi.protocol.commands import UserMessage
from miqi.runtime.app_server import AppServer, AppServerError
from miqi.runtime.turn_event_adapter import CodexTurnEventAdapter
from miqi.runtime.turn_protocol import (
    TurnProtocolError,
    input_attachments,
    input_media,
    input_text,
    normalize_turn_input,
    turn_view,
)


# ── helpers ────────────────────────────────────────────────────────────────


async def _require_session(registry: Any, client_id: str, session_id: str | None) -> Any:
    if session_id is None:
        raise AppServerError("session_id is required", code="INVALID_PARAMS")
    session = await registry.get_session(client_id, session_id)
    if session is None:
        raise AppServerError("Not authorized", code="UNAUTHORIZED")
    return session


def _turn_id() -> str:
    return f"turn-{str(uuid.uuid4())[:12]}"


# ── event drain ────────────────────────────────────────────────────────────


async def _drain_turn_events(
    *,
    server: AppServer,
    session: Any,
    request_id: str,
    thread_id: str,
    turn_id: str,
    input_items: list[dict[str, Any]],
    client_user_message_id: str | None,
) -> None:
    adapter = CodexTurnEventAdapter(
        thread_id=thread_id,
        turn_id=turn_id,
        input_items=input_items,
        client_user_message_id=client_user_message_id,
    )
    while True:
        event = await session.next_event(timeout=300)
        if event is None:
            await server.emit_event(
                session.session_id,
                "error",
                {"error": {"message": "Turn timed out after 300s"}},
                request_id=request_id,
            )
            await server.emit_event(
                session.session_id,
                "turn/completed",
                {"turn": turn_view(turn_id, thread_id, "failed", error_message="Turn timed out after 300s")},
                request_id=request_id,
            )
            return

        for projected in adapter.project(event):
            await server.emit_event(
                session.session_id,
                projected["event"],
                projected["data"],
                request_id=request_id,
            )

        event_type = getattr(event, "type", "")
        if event_type in {"turn_complete", "turn_aborted", "error"}:
            return


# ── registration ───────────────────────────────────────────────────────────


def register_codex_turn_handlers(server: AppServer) -> None:
    """Register Codex-style turn, compact, and inject handlers on AppServer."""

    # ── turn/start ────────────────────────────────────────────────────────

    async def _turn_start(request_id, params, client_id, session_id, registry):
        session = await _require_session(registry, client_id, session_id)
        thread_id = params.get("threadId") or params.get("thread_id")
        if not thread_id:
            raise AppServerError("threadId is required", code="INVALID_PARAMS")
        try:
            input_items = normalize_turn_input(params.get("input"))
        except TurnProtocolError as exc:
            raise AppServerError(str(exc), code="INVALID_PARAMS") from exc

        content = input_text(input_items)
        if not content:
            raise AppServerError(
                "turn/start requires at least one text input item in Phase 41",
                code="INVALID_PARAMS",
            )

        turn_id = _turn_id()
        client_msg_id = params.get("clientUserMessageId")

        server.subscribe(client_id, session.session_id)

        await session.submit(UserMessage(
            content=content,
            thread_id=thread_id,
            media=input_media(input_items),
            attachments=input_attachments(input_items),
            turn_id=turn_id,
            input_items=input_items,
            client_user_message_id=client_msg_id,
            settings_overrides={
                key: params[key]
                for key in (
                    "cwd", "model", "approvalPolicy", "sandboxPolicy", "permissions",
                    "effort", "summary", "personality", "outputSchema",
                    "runtimeWorkspaceRoots", "environments",
                )
                if key in params
            },
        ))

        server.create_background_task(
            _drain_turn_events(
                server=server,
                session=session,
                request_id=request_id,
                thread_id=thread_id,
                turn_id=turn_id,
                input_items=input_items,
                client_user_message_id=client_msg_id,
            ),
            name=f"turn-drain:{session.session_id}:{turn_id}",
        )

        return {"result": {"turn": turn_view(turn_id, thread_id, "inProgress")}}

    # ── turn/interrupt ────────────────────────────────────────────────────

    async def _turn_interrupt(request_id, params, client_id, session_id, registry):
        session = await _require_session(registry, client_id, session_id)
        thread_id = params.get("threadId") or params.get("thread_id")
        turn_id = params.get("turnId") or params.get("turn_id")
        if not thread_id or not turn_id:
            raise AppServerError("threadId and turnId are required", code="INVALID_PARAMS")
        accepted = await session.interrupt_turn(thread_id=thread_id, turn_id=turn_id)
        if not accepted:
            raise AppServerError("Active turn not found", code="INVALID_REQUEST")
        return {"result": {}}

    # ── turn/steer ────────────────────────────────────────────────────────

    async def _turn_steer(request_id, params, client_id, session_id, registry):
        session = await _require_session(registry, client_id, session_id)
        thread_id = params.get("threadId") or params.get("thread_id")
        expected_turn_id = params.get("expectedTurnId") or params.get("expected_turn_id")
        if not thread_id or not expected_turn_id:
            raise AppServerError("threadId and expectedTurnId are required", code="INVALID_PARAMS")
        try:
            input_items = normalize_turn_input(params.get("input"))
        except TurnProtocolError as exc:
            raise AppServerError(str(exc), code="INVALID_PARAMS") from exc
        content = input_text(input_items)
        if not content:
            raise AppServerError(
                "turn/steer requires at least one text input item in Phase 41",
                code="INVALID_PARAMS",
            )
        accepted = await session.steer_turn(
            thread_id=thread_id,
            expected_turn_id=expected_turn_id,
            content=content,
            input_items=input_items,
            client_user_message_id=params.get("clientUserMessageId"),
        )
        if not accepted:
            raise AppServerError("Active turn not steerable", code="INVALID_REQUEST")
        return {"result": {"turnId": expected_turn_id}}

    # ── register ──────────────────────────────────────────────────────────

    server.register_method("turn/start", _turn_start)
    server.register_method("turn/interrupt", _turn_interrupt)
    server.register_method("turn/steer", _turn_steer)
