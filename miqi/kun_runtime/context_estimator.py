"""Context token estimator for KUN runtime.

Estimates token counts for TurnItems and model requests.
Aligns with KUN ``loop/model-request-estimator.ts`` and ``loop/context-estimator.ts``.
"""

from __future__ import annotations

from typing import Any

# Rough heuristic: 4 characters ≈ 1 token for English text.
# This is deliberately simple; exact token counts would require tiktoken.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def estimate_item_tokens(item: dict[str, Any]) -> int:
    """Estimate token count for a TurnItem dict."""
    kind = item.get("kind", "")
    total = 0

    if kind == "user_message":
        total += estimate_tokens(str(item.get("text", "")))
    elif kind == "assistant_text":
        total += estimate_tokens(str(item.get("text", "")))
    elif kind == "assistant_reasoning":
        total += estimate_tokens(str(item.get("text", "")))
    elif kind == "tool_call":
        total += estimate_tokens(str(item.get("summary", "")))
        args = item.get("arguments", {})
        total += estimate_tokens(_json_str(args))
    elif kind == "tool_result":
        output = item.get("output", "")
        total += estimate_tokens(str(output))
    elif kind == "compaction":
        total += estimate_tokens(str(item.get("summary", "")))
    elif kind == "error":
        total += estimate_tokens(str(item.get("message", "")))

    return max(1, total)


def estimate_items_tokens(items: list[dict[str, Any]]) -> int:
    """Estimate total token count for a list of TurnItem dicts."""
    return sum(estimate_item_tokens(item) for item in items)


def estimate_model_request_input_tokens(
    system_prompt: str = "",
    context_instructions: list[str] | None = None,
    history: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> int:
    """Estimate total input tokens for a model request."""
    total = 0
    total += estimate_tokens(system_prompt)
    for instr in (context_instructions or []):
        total += estimate_tokens(instr)
    for item in (history or []):
        total += estimate_item_tokens(item)
    for tool in (tools or []):
        desc = tool.get("description", "")
        total += estimate_tokens(desc)
    return max(1, total)


def _json_str(value: Any) -> str:
    import json
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)
