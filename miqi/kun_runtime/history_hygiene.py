"""Request history hygiene for KUN runtime — trim oversized tool results before sending to model.

Aligns with KUN ``loop/request-history-hygiene.ts``.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_TOOL_RESULT_LINES = 320
DEFAULT_MAX_TOOL_RESULT_BYTES = 32 * 1024
DEFAULT_MAX_TOOL_RESULT_TOKENS = 8_000


def apply_request_history_hygiene(
    items: list[dict[str, Any]],
    max_lines: int = DEFAULT_MAX_TOOL_RESULT_LINES,
    max_bytes: int = DEFAULT_MAX_TOOL_RESULT_BYTES,
    max_tokens: int = DEFAULT_MAX_TOOL_RESULT_TOKENS,
) -> list[dict[str, Any]]:
    """Trim oversized tool results in-place (returns new list)."""
    result: list[dict[str, Any]] = []
    for item in items:
        if item.get("kind") == "tool_result":
            output = item.get("output")
            if isinstance(output, str) and _is_oversized(output, max_lines, max_bytes, max_tokens):
                trimmed = _trim_text(output, max_lines, max_bytes)
                item = {**item, "output": trimmed}
        result.append(item)
    return result


def _is_oversized(text: str, max_lines: int, max_bytes: int, max_tokens: int) -> bool:
    lines = text.split("\n")
    return len(lines) > max_lines or len(text.encode("utf-8")) > max_bytes or (len(text) // 4) > max_tokens


def _trim_text(text: str, max_lines: int, max_bytes: int) -> str:
    """Keep head + tail lines, with signal-line preservation."""
    encoded = text.encode("utf-8")
    lines = text.split("\n")
    if len(lines) <= max_lines and len(encoded) <= max_bytes:
        return text

    # Single-line oversized: just truncate to max_bytes
    if len(lines) == 1:
        marker = f"\n[cache hygiene: showing {max_bytes}B of {len(encoded)}B]"
        return text[:max_bytes - len(marker.encode("utf-8"))] + marker

    head = min(80, max(1, max_lines // 4))
    tail = min(120, max(1, max_lines // 3))

    selected: set[int] = set()
    for i in range(min(head, len(lines))):
        selected.add(i)
    for i in range(max(0, len(lines) - tail), len(lines)):
        selected.add(i)

    signal_count = 0
    for i, line in enumerate(lines):
        if _is_signal_line(line) and signal_count < 48:
            selected.add(i)
            signal_count += 1

    sorted_lines = [lines[i] for i in sorted(selected)[:max_lines]]

    # Fit to byte budget
    result: list[str] = []
    byte_count = 0
    marker = f"\n[cache hygiene: showing {len(sorted_lines)} of {len(lines)} lines]"
    marker_bytes = len(marker.encode("utf-8"))
    for line in sorted_lines:
        lb = len(line.encode("utf-8")) + (1 if result else 0)
        if byte_count + lb + marker_bytes > max_bytes:
            break
        result.append(line)
        byte_count += lb

    return "\n".join(result) + marker


def _is_signal_line(line: str) -> bool:
    import re
    return bool(re.search(
        r"\b(error|failed?|fatal|panic|exception|traceback|warning|warn|"
        r"denied|timeout|timed out|not found|cannot|invalid)\b",
        line, re.IGNORECASE,
    ))
