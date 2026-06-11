"""Context runtime — manages turn message history and context compaction.

Handles building initial messages, adding assistant messages, adding
tool result messages, and compacting long conversation history.
Centralizes message manipulation that was previously scattered across
AgentLoop and ContextBuilder.

Phase 19: adds CompactionResult, estimate_tokens, compress_messages,
compact_thread, and should_auto_compact for runtime-owned context
compaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompactionResult:
    """Result of a context compaction operation."""

    thread_id: str
    messages_before: int
    messages_after: int
    tokens_saved: int
    replacement_messages: list[dict[str, Any]]


class ContextRuntime:
    """Message builder and context compactor for turn execution.

    Phase 12: basic message building (build_initial_messages,
    add_assistant_message, add_tool_result).

    Phase 19: runtime-owned context compaction (estimate_tokens,
    compress_messages, compact_thread, should_auto_compact).
    """

    # ── Phase 12: message building ──────────────────────────────────────

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

    # ── Phase 19: context compaction ────────────────────────────────────

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate token count from messages (chars / 4 heuristic).

        Counts content and tool_calls for each message.
        Returns at least 1.
        """
        chars = 0
        for message in messages:
            chars += len(str(message.get("content") or ""))
            if message.get("tool_calls"):
                chars += len(str(message["tool_calls"]))
        return max(1, chars // 4)

    async def compress_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        """Compress messages into a compact representation.

        Default implementation is a no-op — returns messages unchanged.
        Subclasses or tests override with real compression logic
        (e.g. ContextCompressor from miqi.agent.context_compressor).
        """
        return messages

    async def compact_thread(
        self,
        *,
        history_runtime: Any,
        thread_id: str,
        turn_id: str,
        model: str,
    ) -> CompactionResult:
        """Load thread history, compress it, and persist replacement.

        Returns a CompactionResult with before/after counts and token savings.
        Calls history_runtime.replace_messages_with_compaction() to persist.
        """
        messages = await history_runtime.load_messages(thread_id)
        before_tokens = self.estimate_tokens(messages)
        replacement = await self.compress_messages(
            messages,
            model=model,
            session_id=thread_id,
        )
        after_tokens = self.estimate_tokens(replacement)
        await history_runtime.replace_messages_with_compaction(
            thread_id,
            turn_id,
            replacement,
        )
        return CompactionResult(
            thread_id=thread_id,
            messages_before=len(messages),
            messages_after=len(replacement),
            tokens_saved=max(0, before_tokens - after_tokens),
            replacement_messages=replacement,
        )

    def should_auto_compact(
        self,
        messages: list[dict[str, Any]],
        token_limit: int,
    ) -> bool:
        """Return True when estimated tokens exceed the configured limit."""
        return self.estimate_tokens(messages) >= token_limit
