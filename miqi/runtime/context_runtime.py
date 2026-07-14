"""Context runtime — manages turn message history and context compaction.

Handles building initial messages, adding assistant messages, adding
tool result messages, and compacting long conversation history.
Centralizes message manipulation that was previously scattered across
the legacy AgentLoop and ContextBuilder.
(Historical: AgentLoop removed in Phase 48.)

Phase 19: adds CompactionResult, estimate_tokens, compress_messages,
compact_thread, and should_auto_compact for runtime-owned context
compaction.

Phase 19 follow-up: wires real ContextCompressor via llm_call_fn
injection so compress_messages() actually compresses through the
5-phase algorithm from miqi.agent.context_compressor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from miqi.execution.hook_runtime import (
    HookPoint,
    HookRuntime,
    LifecycleHookContext,
)


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

    When llm_call_fn is provided, compress_messages() delegates to
    ContextCompressor (5-phase algorithm) for real compression.
    Without it, compress_messages() is an explicit no-op.
    """

    def __init__(
        self,
        *,
        llm_call_fn: Callable[
            [list[dict[str, Any]], str], Awaitable[str]
        ] | None = None,
        context_limit_chars: int = 0,
        compression_threshold_chars: int = 0,
        hooks: HookRuntime | None = None,
    ):
        self._compressor: Any = None
        self._compression_threshold_chars = compression_threshold_chars
        self._hooks = hooks
        if llm_call_fn is not None:
            from miqi.agent.context_compressor import ContextCompressor
            self._compressor = ContextCompressor(
                llm_call_fn=llm_call_fn,
                context_limit_chars=context_limit_chars,
            )

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
        """Estimate token count from messages (chars / 2.5 heuristic).

        Counts content and tool_calls for each message.
        Returns at least 1.
        """
        chars = 0
        for message in messages:
            chars += len(str(message.get("content") or ""))
            if message.get("tool_calls"):
                chars += len(str(message["tool_calls"]))
        return max(1, int(chars / 2.5))

    async def compress_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        """Compress messages using ContextCompressor when configured.

        When _compressor is None (no llm_call_fn provided), returns
        messages unchanged as an explicit no-op.
        When _compressor is set, delegates to the 5-phase compression
        algorithm from miqi.agent.context_compressor.

        Phase 51.3: fires PRE_COMPACT and POST_COMPACT lifecycle hooks. A
        PRE_COMPACT block outcome skips the actual compression but still
        fires POST_COMPACT.
        """
        if self._hooks is not None:
            pre_ctx = LifecycleHookContext(
                hook_point=HookPoint.PRE_COMPACT,
                data={
                    "session_id": session_id,
                    "model": model,
                    "message_count": len(messages),
                },
            )
            outcome = await self._hooks.run_with_outcome(
                HookPoint.PRE_COMPACT, pre_ctx
            )
            if outcome.action == "block":
                await self._hooks.run(
                    HookPoint.POST_COMPACT,
                    LifecycleHookContext(
                        hook_point=HookPoint.POST_COMPACT,
                        data={
                            "session_id": session_id,
                            "model": model,
                            "message_count": len(messages),
                            "blocked": True,
                        },
                    ),
                )
                return messages

        if self._compressor is None:
            result = messages
        elif self._compression_threshold_chars > 0:
            total_chars = sum(len(str(m.get("content") or "")) for m in messages)
            if total_chars < self._compression_threshold_chars:
                result = messages
            else:
                result = await self._compressor.compress(
                    messages, model=model, session_id=session_id,
                )
        else:
            result = await self._compressor.compress(
                messages, model=model, session_id=session_id,
            )

        if self._hooks is not None:
            await self._hooks.run(
                HookPoint.POST_COMPACT,
                LifecycleHookContext(
                    hook_point=HookPoint.POST_COMPACT,
                    data={
                        "session_id": session_id,
                        "model": model,
                        "message_count": len(result),
                    },
                ),
            )
        return result

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
        Calls history_runtime.replace_messages_with_compaction() to persist
        with full audit metadata.
        """
        messages = await history_runtime.load_messages(thread_id)
        before_tokens = self.estimate_tokens(messages)
        replacement = await self.compress_messages(
            messages,
            model=model,
        )
        after_tokens = self.estimate_tokens(replacement)
        await history_runtime.replace_messages_with_compaction(
            thread_id,
            turn_id,
            replacement,
            messages_before=len(messages),
            messages_after=len(replacement),
            tokens_saved=max(0, before_tokens - after_tokens),
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

    # ── Phase 56: pre-send context guard ───────────────────────────────

    # Per-model maximum input tokens. Conservative defaults for models that
    # don't explicitly advertise their limit. When the model isn't listed,
    # we fall back to 128K — safe for most modern models.
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

    # Fraction of model max to use as hard limit (80% leaves headroom for
    # the response tokens, tool definitions, and estimation error).
    _CONTEXT_SAFETY_FACTOR = 0.80

    def trim_for_model(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> list[dict[str, Any]]:
        """Hard-trim messages to fit within the model's input token limit.

        This is the LAST-RESORT safety net — it runs right before the
        provider call and discards the oldest assistant+tool pairs until
        the estimated token count is under 80% of the model's maximum.

        Always keeps the system prompt (index 0 if role=='system') and at
        least the last user message. Returns messages unchanged when they
        already fit.
        """
        max_input = self._resolve_model_max_input(model)
        hard_limit = int(max_input * self._CONTEXT_SAFETY_FACTOR)
        est = self.estimate_tokens(messages)

        if est <= hard_limit:
            return messages

        logger.warning(
            "Pre-send guard: estimated {} tokens exceeds {} limit for {} "
            "(model max={}); trimming oldest pairs",
            est, hard_limit, model, max_input,
        )

        work = list(messages)
        system_idx = 0 if work and work[0].get("role") == "system" else -1
        head_protect = max(system_idx + 1, 0) + 1  # system prompt + 1 extra

        while len(work) > head_protect + 1:
            est = self.estimate_tokens(work)
            if est <= hard_limit:
                break

            # Find the oldest cuttable message pair: assistant [+ tool(s)]
            cut_start = None
            for i in range(head_protect, len(work) - 1):
                role = work[i].get("role")
                if role in ("assistant", "tool"):
                    cut_start = i
                    break
            if cut_start is None:
                break

            # Collect a single message to drop
            removed = work.pop(cut_start)

        est_after = self.estimate_tokens(work)
        logger.info(
            "Pre-send guard: messages {} -> {} (est tokens {} -> {})",
            len(messages), len(work), est, est_after,
        )
        return work

    def _resolve_model_max_input(self, model: str) -> int:
        """Return the maximum input tokens for a model name.

        Matches by substring against the known model table, falling back
        to 128K for models not in the table.
        """
        model_lower = model.lower()
        for key, limit in self._MODEL_MAX_INPUT_TOKENS.items():
            if key in model_lower:
                return limit
        return 128_000
