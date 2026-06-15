"""Codex-style turn protocol helpers.

Pure helpers only: no RuntimeSession, no AppServer, no bridge imports.
"""

from __future__ import annotations

from typing import Any


class TurnProtocolError(ValueError):
    """Invalid Codex-style turn protocol input."""


_ALLOWED_INPUT_TYPES = {"text", "image", "localImage", "skill", "mention"}


def normalize_turn_input(raw_input: Any) -> list[dict[str, Any]]:
    """Validate and normalize Codex turn input items."""
    if not isinstance(raw_input, list):
        raise TurnProtocolError("input must be a list")
    if not raw_input:
        raise TurnProtocolError("input must contain at least one item")

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_input):
        if not isinstance(item, dict):
            raise TurnProtocolError(f"input[{index}] must be an object")
        item_type = item.get("type")
        if item_type not in _ALLOWED_INPUT_TYPES:
            raise TurnProtocolError(f"input[{index}].type is unsupported")
        copied = dict(item)
        if item_type == "text":
            text = copied.get("text")
            if not isinstance(text, str) or not text:
                raise TurnProtocolError(f"input[{index}].text must be a non-empty string")
        if item_type == "image":
            url = copied.get("url")
            if not isinstance(url, str) or not url:
                raise TurnProtocolError(f"input[{index}].url must be a non-empty string")
        if item_type == "localImage":
            path = copied.get("path")
            if not isinstance(path, str) or not path:
                raise TurnProtocolError(f"input[{index}].path must be a non-empty string")
        if item_type in {"skill", "mention"}:
            name = copied.get("name")
            path = copied.get("path")
            if not isinstance(name, str) or not name:
                raise TurnProtocolError(f"input[{index}].name must be a non-empty string")
            if not isinstance(path, str) or not path:
                raise TurnProtocolError(f"input[{index}].path must be a non-empty string")
        items.append(copied)
    return items


def input_text(input_items: list[dict[str, Any]]) -> str:
    """Return the provider-visible text for Codex input items."""
    parts = [
        item["text"]
        for item in input_items
        if item.get("type") == "text" and isinstance(item.get("text"), str)
    ]
    return "\n".join(parts).strip()


def input_media(input_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return image URL inputs in MiQi UserMessage.media shape."""
    return [
        {"type": "image", "url": item["url"]}
        for item in input_items
        if item.get("type") == "image"
    ]


def input_attachments(input_items: list[dict[str, Any]]) -> list[str]:
    """Return local image paths as MiQi UserMessage.attachments."""
    return [
        item["path"]
        for item in input_items
        if item.get("type") == "localImage"
    ]


def turn_view(
    turn_id: str,
    thread_id: str,
    status: str,
    *,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Return the Codex turn object used in responses and notifications."""
    return {
        "id": turn_id,
        "threadId": thread_id,
        "status": status,
        "items": [],
        "error": {"message": error_message} if error_message else None,
    }


def user_message_item(
    *,
    turn_id: str,
    input_items: list[dict[str, Any]],
    client_user_message_id: str | None,
) -> dict[str, Any]:
    """Return a Codex userMessage item."""
    item = {
        "type": "userMessage",
        "id": f"{turn_id}:user",
        "content": input_items,
    }
    if client_user_message_id is not None:
        item["clientId"] = client_user_message_id
    return item


def agent_message_item(turn_id: str, text: str) -> dict[str, Any]:
    return {"type": "agentMessage", "id": f"{turn_id}:agent", "text": text}


def reasoning_item(turn_id: str, content: str) -> dict[str, Any]:
    return {"type": "reasoning", "id": f"{turn_id}:reasoning", "summary": content, "content": ""}


def command_execution_item(
    *,
    item_id: str,
    command: str,
    cwd: str,
    status: str,
    aggregated_output: str = "",
    exit_code: int | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": "commandExecution",
        "id": item_id,
        "command": command,
        "cwd": cwd,
        "status": status,
        "commandActions": [],
    }
    if aggregated_output:
        item["aggregatedOutput"] = aggregated_output
    if exit_code is not None:
        item["exitCode"] = exit_code
    if duration_ms is not None:
        item["durationMs"] = duration_ms
    return item


def dynamic_tool_item(
    *,
    item_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    result: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": "dynamicToolCall",
        "id": item_id,
        "tool": tool_name,
        "arguments": arguments,
        "status": status,
    }
    if result is not None:
        item["result"] = result
    return item


def mcp_tool_item(
    *,
    item_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    result: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    server, _, tool = tool_name.partition(".")
    item: dict[str, Any] = {
        "type": "mcpToolCall",
        "id": item_id,
        "server": server or "mcp",
        "tool": tool or tool_name,
        "arguments": arguments,
        "status": status,
    }
    if result is not None:
        item["result"] = result
    if error is not None:
        item["error"] = error
    return item


def context_compaction_item(turn_id: str, *, status: str) -> dict[str, Any]:
    return {
        "type": "contextCompaction",
        "id": f"{turn_id}:contextCompaction",
        "status": status,
    }


def injected_message_to_provider_message(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw injected Responses-style item to provider history shape."""
    if item.get("type") != "message":
        raise TurnProtocolError("Only message items can be injected in Phase 41")
    role = item.get("role")
    if role not in {"user", "assistant", "system", "tool"}:
        raise TurnProtocolError("Injected message role is unsupported")

    raw_content = item.get("content", "")
    if isinstance(raw_content, str):
        content = raw_content
    elif isinstance(raw_content, list):
        parts: list[str] = []
        for part in raw_content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        content = "\n".join(parts)
    else:
        content = ""

    return {
        "role": role,
        "content": content,
        "message_fields": {"raw_item": item},
    }
