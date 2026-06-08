"""Context compactor for KUN runtime — fold long histories into compaction summaries.

Aligns with KUN ``loop/context-compactor.ts``.
"""

from __future__ import annotations

from typing import Any

from miqi.kun_runtime.context_estimator import estimate_items_tokens

DEFAULT_SOFT_THRESHOLD = 60_000  # tokens
DEFAULT_HARD_THRESHOLD = 128_000  # tokens


class ContextCompactor:
    """Folds long TurnItem histories into compaction summaries."""

    def __init__(
        self,
        soft_threshold: int = DEFAULT_SOFT_THRESHOLD,
        hard_threshold: int = DEFAULT_HARD_THRESHOLD,
    ):
        self.soft_threshold = soft_threshold
        self.hard_threshold = hard_threshold

    def estimate(self, items: list[dict[str, Any]]) -> int:
        return estimate_items_tokens(items)

    def plan_compaction(
        self, items: list[dict[str, Any]], model: str = "", prompt_tokens: int | None = None
    ) -> dict[str, Any] | None:
        """Return a compaction plan or None if not needed."""
        estimated = self.estimate(items)
        tokens = max(estimated, prompt_tokens or 0)

        if tokens < self.soft_threshold:
            return None

        if tokens >= self.hard_threshold:
            mode = "force"
            keep_recent = 1
        elif tokens >= self.soft_threshold + (self.hard_threshold - self.soft_threshold) * 0.6:
            mode = "aggressive"
            keep_recent = 2
        else:
            mode = "normal"
            keep_recent = 4

        return {
            "mode": mode,
            "keepRecent": keep_recent,
            "reason": f"estimated {tokens} tokens reached {mode} compaction threshold",
        }

    def compact(
        self,
        thread_id: str,
        turn_id: str,
        history: list[dict[str, Any]],
        pinned_constraints: list[str] | None = None,
        keep_recent: int = 4,
        reason: str = "",
        mode: str = "normal",
        summary_override: str | None = None,
    ) -> dict[str, Any]:
        """Compact history. Returns {next, summaryItem, replacedTokens}."""
        pinned = pinned_constraints or []
        frozen: list[dict[str, Any]] = []

        # Trim trailing incomplete tool calls
        work = _trim_trailing_tool_calls(history)

        keep = min(keep_recent, len(work) - 1) if len(work) > 1 else len(work)
        if len(work) <= 1 or len(work) - keep <= 0:
            summary_item = {
                "id": f"compaction_{turn_id}_noop",
                "turnId": turn_id,
                "threadId": thread_id,
                "role": "system",
                "status": "completed",
                "kind": "compaction",
                "createdAt": _now_iso(),
                "summary": "no compaction needed",
                "replacedTokens": 0,
                "pinnedConstraints": pinned,
            }
            return {"next": [*frozen, *work], "summaryItem": summary_item, "replacedTokens": 0}

        head = work[:len(work) - keep]
        tail = work[-keep:]
        replaced_tokens = estimate_items_tokens(head)

        summary = summary_override or _build_compaction_summary(work, head, tail, pinned, reason, mode)
        summary_item = {
            "id": f"compaction_{turn_id}_{_ts()}",
            "turnId": turn_id,
            "threadId": thread_id,
            "role": "system",
            "status": "completed",
            "kind": "compaction",
            "createdAt": _now_iso(),
            "summary": summary,
            "replacedTokens": replaced_tokens,
            "pinnedConstraints": pinned,
            "sourceItemIds": [item.get("id", "") for item in head if item.get("id")],
        }

        return {"next": [*frozen, summary_item, *tail], "summaryItem": summary_item, "replacedTokens": replaced_tokens}

    def should_compact(self, items: list[dict[str, Any]], model: str = "") -> bool:
        return self.plan_compaction(items, model) is not None


def _build_compaction_summary(
    history: list[dict[str, Any]],
    head: list[dict[str, Any]],
    tail: list[dict[str, Any]],
    pinned: list[str],
    reason: str,
    mode: str,
) -> str:
    lines: list[str] = []
    if reason:
        lines.append(f"Reason: {reason}")
    if mode:
        lines.append(f"Mode: {mode}")
    lines.append("Pinned constraints (preserved across compaction):")
    for p in pinned:
        lines.append(f"- {p}")
    lines.append("")
    lines.append(f"Summarized {len(head)} item(s); {len(tail)} recent item(s) kept verbatim.")
    lines.append("Conversation summary:")

    for item in head:
        line = _summarize_item(item)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _summarize_item(item: dict[str, Any]) -> str:
    kind = item.get("kind", "")
    if kind == "user_message":
        return f"- User: {_clip(item.get('text', ''))}"
    elif kind == "assistant_text":
        return f"- Assistant: {_clip(item.get('text', ''))}"
    elif kind == "assistant_reasoning":
        return ""
    elif kind == "tool_call":
        return f"- Tool call {item.get('toolName', '')}: {_clip(item.get('summary', '') or str(item.get('arguments', '')))}"
    elif kind == "tool_result":
        err = " error" if item.get("isError") else ""
        return f"- Tool result {item.get('toolName', '')}{err}: {_clip(str(item.get('output', '')))}"
    elif kind == "compaction":
        return f"- Earlier compaction: {_clip(item.get('summary', ''), 600)}"
    elif kind == "error":
        return f"- Error: {_clip(item.get('message', ''))}"
    return ""


def _clip(text: str, max_chars: int = 360) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= max_chars:
        return compacted
    return f"{compacted[:max_chars - 3].strip()}..."


def _trim_trailing_tool_calls(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    end = len(history)
    while end > 0 and history[end - 1].get("kind") == "tool_call":
        end -= 1
    return history[:end]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ts() -> int:
    import time
    return int(time.time() * 1000)
