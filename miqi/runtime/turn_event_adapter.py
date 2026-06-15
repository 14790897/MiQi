"""Project MiQi runtime events into Codex turn/item notifications."""

from __future__ import annotations

from typing import Any

from miqi.protocol.events import (
    AgentMessageDeltaEvent,
    AgentMessageEvent,
    AgentReasoningEvent,
    ApprovalRequestedEvent,
    ContextCompactedEvent,
    ErrorEvent,
    ExecCommandBeginEvent,
    ExecCommandEndEvent,
    ExecCommandOutputDeltaEvent,
    ToolCallBeginEvent,
    ToolCallEndEvent,
    TurnAbortedEvent,
    TurnCompleteEvent,
    TurnStartedEvent,
)
from miqi.runtime.turn_protocol import (
    agent_message_item,
    command_execution_item,
    context_compaction_item,
    dynamic_tool_item,
    mcp_tool_item,
    reasoning_item,
    turn_view,
    user_message_item,
)


class CodexTurnEventAdapter:
    """Projects MiQi runtime events into Codex turn/item notifications.

    Stateful: tracks which items have been started/completed to avoid
    duplicate emissions and to aggregate streaming content.
    """

    def __init__(
        self,
        *,
        thread_id: str,
        turn_id: str,
        input_items: list[dict[str, Any]],
        client_user_message_id: str | None,
    ):
        self.thread_id = thread_id
        self.turn_id = turn_id
        self.input_items = input_items
        self.client_user_message_id = client_user_message_id
        self._user_item_emitted = False
        self._agent_started = False
        self._agent_completed = False
        self._agent_text_parts: list[str] = []
        self._reasoning_started = False
        self._reasoning_text_parts: list[str] = []
        self._commands: dict[str, dict[str, Any]] = {}
        self._command_output: dict[str, list[str]] = {}
        self._tool_items: dict[str, dict[str, Any]] = {}

    # ── helpers ───────────────────────────────────────────────────────────

    def _notification(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"event": event, "data": data}

    def _with_location(self, data: dict[str, Any]) -> dict[str, Any]:
        data["threadId"] = self.thread_id
        data["turnId"] = self.turn_id
        return data

    # ── dispatch ──────────────────────────────────────────────────────────

    def project(self, event: Any) -> list[dict[str, Any]]:
        handler = getattr(self, f"_on_{type(event).__name__}", None)
        if handler is not None:
            return handler(event)
        return []

    # ── TurnStartedEvent ──────────────────────────────────────────────────

    def _on_TurnStartedEvent(self, event: TurnStartedEvent) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []

        # Emit turn/started
        result.append(self._notification(
            "turn/started",
            self._with_location({
                "turn": turn_view(self.turn_id, self.thread_id, "inProgress"),
            }),
        ))

        # Emit user message item start + complete
        if not self._user_item_emitted:
            self._user_item_emitted = True
            user_item = user_message_item(
                turn_id=self.turn_id,
                input_items=self.input_items,
                client_user_message_id=self.client_user_message_id,
            )
            result.append(self._notification(
                "item/started",
                self._with_location({"item": user_item}),
            ))
            result.append(self._notification(
                "item/completed",
                self._with_location({"item": user_item}),
            ))

        return result

    # ── AgentMessageDeltaEvent ────────────────────────────────────────────

    def _on_AgentMessageDeltaEvent(self, event: AgentMessageDeltaEvent) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not self._agent_started:
            self._agent_started = True
            result.append(self._notification(
                "item/started",
                self._with_location({
                    "item": {"type": "agentMessage", "id": f"{self.turn_id}:agent"},
                }),
            ))
        self._agent_text_parts.append(event.delta)
        result.append(self._notification(
            "item/agentMessage/delta",
            self._with_location({
                "itemId": f"{self.turn_id}:agent",
                "delta": event.delta,
            }),
        ))
        return result

    # ── AgentMessageEvent ─────────────────────────────────────────────────

    def _on_AgentMessageEvent(self, event: AgentMessageEvent) -> list[dict[str, Any]]:
        if self._agent_completed:
            return []
        self._agent_completed = True
        # Ensure started once
        result: list[dict[str, Any]] = []
        if not self._agent_started:
            self._agent_started = True
            result.append(self._notification(
                "item/started",
                self._with_location({
                    "item": {"type": "agentMessage", "id": f"{self.turn_id}:agent"},
                }),
            ))
        item = agent_message_item(self.turn_id, event.content)
        result.append(self._notification(
            "item/completed",
            self._with_location({"item": item}),
        ))
        return result

    # ── AgentReasoningEvent ───────────────────────────────────────────────

    def _on_AgentReasoningEvent(self, event: AgentReasoningEvent) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not self._reasoning_started:
            self._reasoning_started = True
            result.append(self._notification(
                "item/started",
                self._with_location({
                    "item": {"type": "reasoning", "id": f"{self.turn_id}:reasoning"},
                }),
            ))
        self._reasoning_text_parts.append(event.content)
        ri = reasoning_item(self.turn_id, event.content)
        result.append(self._notification(
            "item/reasoning/summaryTextDelta",
            self._with_location({
                "itemId": f"{self.turn_id}:reasoning",
                "delta": ri.get("summary", event.content),
            }),
        ))
        return result

    # ── ExecCommandBeginEvent ─────────────────────────────────────────────

    def _on_ExecCommandBeginEvent(self, event: ExecCommandBeginEvent) -> list[dict[str, Any]]:
        item_id = f"{self.turn_id}:exec:{event.tool_call_id}"
        cmd_item = command_execution_item(
            item_id=item_id,
            command=event.command,
            cwd=event.cwd,
            status="inProgress",
        )
        self._commands[event.tool_call_id] = cmd_item
        self._command_output[event.tool_call_id] = []
        return [self._notification(
            "item/started",
            self._with_location({"item": cmd_item}),
        )]

    # ── ExecCommandOutputDeltaEvent ───────────────────────────────────────

    def _on_ExecCommandOutputDeltaEvent(self, event: ExecCommandOutputDeltaEvent) -> list[dict[str, Any]]:
        output_parts = self._command_output.get(event.tool_call_id, [])
        output_parts.append(event.delta)
        self._command_output[event.tool_call_id] = output_parts
        return [self._notification(
            "item/commandExecution/outputDelta",
            self._with_location({
                "itemId": f"{self.turn_id}:exec:{event.tool_call_id}",
                "stream": event.stream,
                "delta": event.delta,
            }),
        )]

    # ── ExecCommandEndEvent ───────────────────────────────────────────────

    def _on_ExecCommandEndEvent(self, event: ExecCommandEndEvent) -> list[dict[str, Any]]:
        item_id = f"{self.turn_id}:exec:{event.tool_call_id}"
        cmd_item = self._commands.get(event.tool_call_id)
        if cmd_item is None:
            return []
        aggregated = "".join(self._command_output.get(event.tool_call_id, []))
        completed = command_execution_item(
            item_id=item_id,
            command=cmd_item.get("command", ""),
            cwd=cmd_item.get("cwd", ""),
            status="completed",
            aggregated_output=aggregated,
            exit_code=event.exit_code,
            duration_ms=event.duration_ms,
        )
        return [self._notification(
            "item/completed",
            self._with_location({"item": completed}),
        )]

    # ── ToolCallBeginEvent ────────────────────────────────────────────────

    def _on_ToolCallBeginEvent(self, event: ToolCallBeginEvent) -> list[dict[str, Any]]:
        # Skip exec tools — handled by exec lifecycle events
        if event.tool_name == "exec":
            return []
        item_id = f"{self.turn_id}:tool:{event.tool_call_id}"
        if event.tool_name.startswith("mcp."):
            item = mcp_tool_item(
                item_id=item_id,
                tool_name=event.tool_name,
                arguments=event.arguments,
                status="inProgress",
            )
        else:
            item = dynamic_tool_item(
                item_id=item_id,
                tool_name=event.tool_name,
                arguments=event.arguments,
                status="inProgress",
            )
        self._tool_items[event.tool_call_id] = item
        return [self._notification(
            "item/started",
            self._with_location({"item": item}),
        )]

    # ── ToolCallEndEvent ──────────────────────────────────────────────────

    def _on_ToolCallEndEvent(self, event: ToolCallEndEvent) -> list[dict[str, Any]]:
        if event.tool_name == "exec":
            return []
        item = self._tool_items.pop(event.tool_call_id, None)
        if item is None:
            return []
        item["status"] = "completed"
        if event.output_preview:
            item["result"] = event.output_preview
        return [self._notification(
            "item/completed",
            self._with_location({"item": item}),
        )]

    # ── ApprovalRequestedEvent ────────────────────────────────────────────

    def _on_ApprovalRequestedEvent(self, event: ApprovalRequestedEvent) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        event_name = (
            "item/commandExecution/requestApproval" if event.category == "exec"
            else "item/fileChange/requestApproval" if event.category == "file_write"
            else None
        )
        if event_name is not None:
            result.append(self._notification(
                event_name,
                self._with_location({
                    "approvalId": event.approval_id,
                    "reason": event.description,
                    "details": event.details,
                }),
            ))
        return result

    # ── ContextCompactedEvent ─────────────────────────────────────────────

    def _on_ContextCompactedEvent(self, event: ContextCompactedEvent) -> list[dict[str, Any]]:
        item = context_compaction_item(self.turn_id, status="completed")
        return [
            self._notification(
                "item/started",
                self._with_location({"item": context_compaction_item(self.turn_id, status="inProgress")}),
            ),
            self._notification(
                "item/completed",
                self._with_location({"item": item}),
            ),
        ]

    # ── TurnCompleteEvent ─────────────────────────────────────────────────

    def _on_TurnCompleteEvent(self, event: TurnCompleteEvent) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []

        # Complete pending agent item if needed
        if self._agent_started and not self._agent_completed:
            self._agent_completed = True
            text = "".join(self._agent_text_parts)
            result.append(self._notification(
                "item/completed",
                self._with_location({"item": agent_message_item(self.turn_id, text)}),
            ))

        # Token usage
        if event.token_usage:
            result.append(self._notification(
                "thread/tokenUsage/updated",
                self._with_location({"tokenUsage": event.token_usage}),
            ))

        # Turn completed
        status = "completed" if event.outcome == "success" else "failed"
        result.append(self._notification(
            "turn/completed",
            self._with_location({
                "turn": turn_view(self.turn_id, self.thread_id, status),
            }),
        ))
        return result

    # ── TurnAbortedEvent ──────────────────────────────────────────────────

    def _on_TurnAbortedEvent(self, event: TurnAbortedEvent) -> list[dict[str, Any]]:
        return [self._notification(
            "turn/completed",
            self._with_location({
                "turn": turn_view(self.turn_id, self.thread_id, "interrupted"),
            }),
        )]

    # ── ErrorEvent ────────────────────────────────────────────────────────

    def _on_ErrorEvent(self, event: ErrorEvent) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = [
            self._notification(
                "error",
                {"error": {"message": event.message, "recoverable": event.recoverable}},
            ),
        ]
        if not event.recoverable:
            result.append(self._notification(
                "turn/completed",
                self._with_location({
                    "turn": turn_view(
                        self.turn_id,
                        self.thread_id,
                        "failed",
                        error_message=event.message,
                    ),
                }),
            ))
        return result
