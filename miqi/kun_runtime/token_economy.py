"""Token economy config and instruction for KUN runtime.

Aligns with KUN ``loop/token-economy.ts``.
"""

from __future__ import annotations

from typing import Any

TOKEN_ECONOMY_INSTRUCTION = (
    "Token economy mode is enabled.\n"
    "Reply concisely: answer directly, skip pleasantries, filler, and hedging.\n"
    "Preserve exact code, commands, paths, URLs, identifiers, and quoted errors.\n"
    "When tool output says content was omitted, use narrower read/grep/bash ranges instead of guessing."
)


def normalize_token_economy_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize token economy config with defaults."""
    defaults = {
        "enabled": False,
        "compress_tool_descriptions": True,
        "compress_tool_results": True,
        "concise_responses": True,
    }
    if config:
        defaults.update(config)
    return defaults
