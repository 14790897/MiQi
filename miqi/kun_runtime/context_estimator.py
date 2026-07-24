"""Context token estimator for KUN runtime.

Estimates token counts for TurnItems and model requests.
Aligns with KUN ``loop/model-request-estimator.ts`` and ``loop/context-estimator.ts``.
"""

from __future__ import annotations

from typing import Any

# Rough heuristic: 2.5 characters ≈ 1 token for mixed content (code, JSON, CJK text).
# Conservative estimate errs on the side of triggering compaction earlier.
_CHARS_PER_TOKEN = 2.5


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string."""
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


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


# Per-model maximum input tokens. Conservative defaults for models that
# don't explicitly advertise their limit.
_MODEL_MAX_INPUT_TOKENS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3": 200_000,
    "o3-mini": 200_000,
    "o4-mini": 200_000,
    "claude-3.5-sonnet": 200_000,
    "claude-3.5-haiku": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-haiku": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-opus-4": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-haiku-4-5": 200_000,
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
    "qwen-max": 131_072,
    "qwen-plus": 131_072,
    "qwen-turbo": 1_000_000,
    "kimi-k2.5": 128_000,
    "kimi-k2": 128_000,
    "glm-4": 128_000,
    "minimax-m1": 1_000_000,
}
_CONTEXT_SAFETY_FACTOR = 0.80


def get_model_max_input_tokens(model: str) -> int:
    """Return the maximum input tokens for a model name (substring match)."""
    model_lower = model.lower()
    for key, limit in _MODEL_MAX_INPUT_TOKENS.items():
        if key in model_lower:
            return limit
    return 128_000


def get_safe_context_limit(model: str) -> int:
    """Return the safe context limit (80% of model max) for a model."""
    return int(get_model_max_input_tokens(model) * _CONTEXT_SAFETY_FACTOR)
