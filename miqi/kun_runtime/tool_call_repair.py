"""Tool call argument repair for KUN runtime.

Aligns with KUN ``loop/tool-call-repair.ts``.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_MAX_STRING_BYTES = 512 * 1024


def repair_dispatch_tool_arguments(
    raw: dict[str, Any],
    tool_name: str = "",
    tool_kind: str | None = None,
    max_string_bytes: int = DEFAULT_MAX_STRING_BYTES,
) -> dict[str, list[str]]:
    """Repair and validate tool arguments. Returns {arguments, notes}."""
    notes: list[str] = []
    current = dict(raw)

    # Flatten wrapper keys like 'arguments', 'args', 'input', 'params'
    flattened = _flatten_wrapper(current)
    if flattened is not None:
        current = flattened["args"]
        notes.append(flattened["note"])
    else:
        scavenged = _scavenge_json_string(current)
        if scavenged is not None:
            current = scavenged["args"]
            notes.append(scavenged["note"])

    # Truncate oversized strings (skip for file_change tools)
    if tool_kind != "file_change":
        truncated, changed, count = _truncate_oversized_strings(current, max_string_bytes)
        if changed:
            current = truncated
            notes.append(f"truncated {count} oversized argument string(s)")

    return {"arguments": current, "notes": notes}


_WRAPPER_KEYS = ("arguments", "args", "input", "parameters", "params", "payload")


def _flatten_wrapper(raw: dict[str, Any]) -> dict[str, Any] | None:
    """If *raw* is a wrapper dict, extract the inner args."""
    for key in _WRAPPER_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, dict):
            return {"args": value, "note": f"flattened {key} wrapper"}
        if isinstance(value, str):
            parsed = _parse_jsonish(value)
            if isinstance(parsed, dict):
                return {"args": parsed, "note": f"flattened {key} wrapper (parsed JSON string)"}
    return None


def _scavenge_json_string(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Try to scavenge a JSON object from a string value."""
    entries = list(raw.items())
    if len(entries) != 1:
        return None
    key, value = entries[0]
    if isinstance(value, dict):
        return {"args": value, "note": f"scavenged object from {key}"}
    if isinstance(value, str):
        parsed = _parse_jsonish(value)
        if isinstance(parsed, dict):
            return {"args": parsed, "note": f"scavenged JSON from {key}"}
    return None


def _parse_jsonish(text: str) -> Any:
    """Try to parse JSON, stripping markdown fences if needed."""
    candidates = [
        text.strip(),
        _strip_markdown_fence(text),
        _extract_first_json_object(text),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _strip_markdown_fence(text: str) -> str:
    import re
    m = re.match(r"^```(?:json|javascript|js)?\s*\n?(.*?)\n?```$", text.strip(), re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _truncate_oversized_strings(
    value: Any, max_bytes: int
) -> tuple[Any, bool, int]:
    """Truncate string values exceeding max_bytes. Returns (value, changed, count)."""
    state = {"changed": False, "count": 0}
    result = _truncate_value(value, max_bytes, state)
    return result, state["changed"], state["count"]


def _truncate_value(value: Any, max_bytes: int, state: dict) -> Any:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) <= max_bytes:
            return value
        state["changed"] = True
        state["count"] += 1
        truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
        return f"{truncated}\n...[truncated by Kun tool argument repair]"
    if isinstance(value, list):
        return [_truncate_value(v, max_bytes, state) for v in value]
    if isinstance(value, dict):
        return {k: _truncate_value(v, max_bytes, state) for k, v in value.items()}
    return value
