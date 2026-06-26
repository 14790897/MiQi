"""History healing and model history repair for KUN runtime.

Aligns with KUN ``loop/history-healing.ts`` and ``domain/model-history-repair.ts``.
"""

from __future__ import annotations

from typing import Any


def heal_loaded_history_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Normalize loaded items and repair orphan tool results / missing tool calls.

    Returns (healed_items, changed).
    """
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        fixed = _normalize_loaded_item(item, idx)
        if fixed is not None:
            normalized.append(fixed)

    repaired = repair_model_history_items(normalized)

    # Check if anything changed
    import json
    changed = json.dumps(items, sort_keys=True, default=str) != json.dumps(repaired, sort_keys=True, default=str)
    return repaired, changed


def repair_model_history_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Repair tool call / tool result pairing issues."""
    if not items:
        return items

    # Collect all tool_call callIds
    call_ids: set[str] = set()
    for item in items:
        if item.get("kind") == "tool_call":
            cid = item.get("callId", "")
            if cid:
                call_ids.add(cid)

    # Collect all tool_result callIds
    result_ids: set[str] = set()
    for item in items:
        if item.get("kind") == "tool_result":
            cid = item.get("callId", "")
            if cid:
                result_ids.add(cid)

    # Build repaired list: drop orphan tool_results, inject stubs for missing results
    repaired: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        kind = item.get("kind", "")

        if kind == "tool_result":
            cid = item.get("callId", "")
            if cid not in call_ids:
                continue  # drop orphan
            repaired.append(item)
            continue

        repaired.append(item)

        # After a tool_call, inject stubs for missing results
        if kind == "tool_call":
            cid = item.get("callId", "")
            if cid and cid not in result_ids:
                repaired.append({
                    "kind": "tool_result",
                    "id": f"item_healed_{cid}_stub",
                    "turnId": item.get("turnId", ""),
                    "threadId": item.get("threadId", ""),
                    "role": "tool",
                    "status": "completed",
                    "createdAt": item.get("createdAt", ""),
                    "toolName": item.get("toolName", ""),
                    "callId": cid,
                    "toolKind": item.get("toolKind", "tool_call"),
                    "output": "[result not available — context was compressed]",
                    "isError": False,
                })

    return repaired


def _normalize_loaded_item(item: dict[str, Any], index: int) -> dict[str, Any] | None:
    """Normalize a single loaded item. Returns None if the item is corrupt."""
    if not isinstance(item, dict):
        return None
    kind = str(item.get("kind", ""))
    if not kind:
        return None

    # Ensure id
    if not item.get("id"):
        item["id"] = f"item_healed_{index}_{kind}"

    # Validate required fields per kind
    if kind == "tool_call":
        if not item.get("callId") or not item.get("toolName"):
            return None
    elif kind == "tool_result":
        if not item.get("callId") or not item.get("toolName"):
            return None

    return item
