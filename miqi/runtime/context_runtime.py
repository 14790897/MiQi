"""Context runtime — manages turn message history.

Handles building initial messages, adding assistant messages, and adding
tool result messages. Centralizes message manipulation that was previously
scattered across AgentLoop and ContextBuilder.
"""

from __future__ import annotations

from typing import Any


class ContextRuntime:
    """Stateless message builder for turn execution."""

    def build_initial_messages(
        self,
        *,
        turn: Any,
        user_content: str,
        system_prompt: str,
        history: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Build the initial message list for a turn.

        Returns [system, *history, user] list suitable for provider.chat.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages

    def add_assistant_message(
        self,
        *,
        messages: list[dict[str, Any]],
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Append an assistant message, optionally with tool_calls."""
        item: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            item["tool_calls"] = tool_calls
        return [*messages, item]

    def add_tool_result(
        self,
        *,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        name: str,
        content: str,
    ) -> list[dict[str, Any]]:
        """Append a tool result message."""
        return [*messages, {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        }]
