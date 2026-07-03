"""Event emitter — translates Runtime Events to Bridge IPC events."""

from __future__ import annotations

from typing import Any


class EventEmitter:
    """Translates typed runtime events to IPC event channels.

    Each runtime event type maps to a specific IPC channel.
    The bridge_send callable is responsible for delivering the
    event to the Electron frontend via the JSON-line protocol.
    """

    def __init__(self, bridge_send):
        """Initialize with a send function.

        Args:
            bridge_send: Callable(channel: str, data: dict) that sends
                         the event to the Electron frontend.
        """
        self._send = bridge_send

    async def emit(self, event: Any) -> None:
        """Emit a runtime event to the appropriate IPC channel.

        Uses structural pattern matching (Python 3.10+) to dispatch
        based on event attributes. Unknown event types are silently
        dropped.
        """
        event_type = getattr(event, "type", None)
        if event_type is None:
            return

        match event_type:
            case "turn_started":
                self._send("turn:started", {
                    "turn_id": event.turn_id,
                    "agent_name": event.agent_name,
                    "thread_id": event.thread_id,
                })

            case "turn_complete":
                self._send("turn:completed", {
                    "turn_id": event.turn_id,
                    "thread_id": event.thread_id,
                    "outcome": event.outcome,
                    "tools_used": event.tools_used,
                    "token_usage": event.token_usage,
                })

            case "turn_aborted":
                self._send("chat:aborted", {
                    "message": f"Turn aborted: {event.reason}",
                })

            case "agent_message_delta":
                self._send("chat:delta", {
                    "turn_id": event.turn_id,
                    "delta": event.delta,
                    "index": event.index,
                })

            case "agent_message":
                self._send("chat:final", {
                    "turn_id": event.turn_id,
                    "content": event.content,
                    "finish_reason": event.finish_reason,
                    "tool_calls": event.tool_calls,
                })

            case "agent_reasoning":
                # Reasoning is logged but not always shown to user
                self._send("chat:progress", {
                    "text": f"\U0001f914 {event.summary or 'Thinking...'}",
                    "tool_hint": False,
                })

            case "tool_call_begin":
                self._send("chat:progress", {
                    "text": f"\U0001f504 {event.tool_display}",
                    "tool_hint": True,
                })

            case "tool_call_end":
                self._send("chat:progress", {
                    "text": f"{'✅' if event.success else '❌'} {event.tool_name} ({event.duration_ms}ms)",
                    "tool_hint": True,
                })

            case "exec_command_begin":
                self._send("chat:progress", {
                    "text": f"▶️ {event.command[:80]}",
                    "tool_hint": True,
                })

            case "exec_command_output_delta":
                self._send("chat:delta", {
                    "stream": event.stream,
                    "delta": event.delta,
                })

            case "exec_command_end":
                self._send("chat:progress", {
                    "text": f"{'✅' if event.exit_code == 0 else '❌'} Exit {event.exit_code} ({event.duration_ms}ms)",
                    "tool_hint": True,
                })

            case "approval_requested":
                self._send("approval:request", {
                    "approval_id": event.approval_id,
                    "command": event.description,
                    "description": event.description,
                    "allow_permanent": event.allow_permanent,
                })

            case "approval_resolved":
                self._send("approval:cleared", {
                    "reason": "resolved",
                })

            case "sub_agent_spawned":
                self._send("agent:spawned", {
                    "sub_agent_id": event.sub_agent_id,
                    "sub_thread_id": event.sub_thread_id,
                    "agent_type": event.agent_type,
                    "task_label": event.task_label,
                })

            case "sub_agent_completed":
                self._send("agent:completed", {
                    "sub_agent_id": event.sub_agent_id,
                    "sub_thread_id": event.sub_thread_id,
                    "outcome": event.outcome,
                    "summary": event.summary,
                })

            case "plan_update":
                self._send("plan:updated", {
                    "plan": event.plan,
                })

            case "error":
                self._send("chat:error", {
                    "message": event.message,
                })

            case "warning":
                self._send("chat:progress", {
                    "text": f"⚠️ {event.message}",
                    "tool_hint": False,
                })

            case "context_compacted":
                # Internal event — log only, don't forward to UI
                pass

            case "session_configured":
                # Internal event — log only
                pass

            case _:
                # Unknown event type — silently ignore
                pass
