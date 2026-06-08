"""Auto model router for KUN runtime.

Aligns with KUN ``loop/auto-model-router.ts``.
Simple first implementation: when mode is 'auto', selects the default model.
Full auto-routing (classifier-based selection) is deferred.
"""

from __future__ import annotations

from typing import Any


async def resolve_auto_model_route(
    candidates: list[str],
    default_model: str = "",
) -> dict[str, Any]:
    """Resolve the model to use from a list of candidates.

    Skips None/empty values and 'auto' entries. Falls back to *default_model*.
    """
    for candidate in candidates:
        c = (candidate or "").strip().lower()
        if not c:
            continue
        if c == "auto":
            continue
        return {"model": candidate, "reasoningEffort": None}

    return {"model": default_model, "reasoningEffort": None}
