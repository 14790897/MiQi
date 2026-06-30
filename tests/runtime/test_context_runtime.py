"""Tests for ContextRuntime (Phase 12.2)."""

import pytest

from miqi.runtime.context_runtime import ContextRuntime


class _FakeTurnContext:
    turn_id = "turn-1"
    thread_id = "thread-1"

    class _Meta:
        name = "code-agent"
    agent_metadata = _Meta()


def test_context_runtime_builds_initial_messages():
    runtime = ContextRuntime()
    turn = _FakeTurnContext()

    messages = runtime.build_initial_messages(
        turn=turn,
        user_content="hello",
        system_prompt="system",
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "hello"


def test_context_runtime_builds_with_history():
    runtime = ContextRuntime()
    turn = _FakeTurnContext()

    messages = runtime.build_initial_messages(
        turn=turn,
        user_content="hello",
        system_prompt="system",
        history=[{"role": "assistant", "content": "previous"}],
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


def test_context_runtime_adds_tool_result():
    runtime = ContextRuntime()
    messages = [{"role": "user", "content": "hello"}]

    updated = runtime.add_tool_result(
        messages=messages,
        tool_call_id="call-1",
        name="read_file",
        content="file content",
    )

    assert updated[-1]["role"] == "tool"
    assert updated[-1]["tool_call_id"] == "call-1"
    assert updated[-1]["name"] == "read_file"
    assert updated[-1]["content"] == "file content"


def test_context_runtime_adds_assistant_message():
    runtime = ContextRuntime()
    messages = [{"role": "user", "content": "hello"}]

    updated = runtime.add_assistant_message(
        messages=messages,
        content="answer",
    )

    assert updated[-1]["role"] == "assistant"
    assert updated[-1]["content"] == "answer"


def test_context_runtime_adds_assistant_with_tool_calls():
    runtime = ContextRuntime()
    messages = [{"role": "user", "content": "hello"}]
    tool_calls = [{"id": "tc-1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]

    updated = runtime.add_assistant_message(
        messages=messages,
        content="",
        tool_calls=tool_calls,
    )

    assert updated[-1]["role"] == "assistant"
    assert updated[-1]["tool_calls"] == tool_calls


# ---------------------------------------------------------------------------
# Phase 19: Context compaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_runtime_compact_thread_replaces_history():
    """compact_thread() reads history, compresses, and replaces via history_runtime."""
    from miqi.runtime.context_runtime import ContextRuntime

    class FakeHistory:
        def __init__(self):
            self.messages = [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ]
            self.replaced = None

        async def load_messages(self, thread_id):
            return list(self.messages)

        async def replace_messages_with_compaction(
            self, thread_id, turn_id, replacement,
            messages_before=0, messages_after=0, tokens_saved=0,
        ):
            self.replaced = replacement

    async def fake_compress(messages, model, session_id=""):
        return [{"role": "system", "content": "[summary]"}, messages[-1]]

    runtime = ContextRuntime()
    runtime.compress_messages = fake_compress
    history = FakeHistory()

    result = await runtime.compact_thread(
        history_runtime=history,
        thread_id="thread-1",
        turn_id="compact-1",
        model="test-model",
    )

    assert result.messages_before == 3
    assert result.messages_after == 2
    assert history.replaced == [
        {"role": "system", "content": "[summary]"},
        {"role": "user", "content": "three"},
    ]


def test_context_runtime_estimate_tokens():
    """estimate_tokens() approximates token count (chars / 4)."""
    runtime = ContextRuntime()
    msgs = [
        {"role": "user", "content": "hello world"},
        {"role": "assistant", "content": "hi"},
    ]
    # "hello world" (11) + "hi" (2) = 13 chars → 13//4 = 3 tokens
    assert runtime.estimate_tokens(msgs) == 3


def test_context_runtime_should_auto_compact():
    """should_auto_compact() returns True when estimated tokens >= limit."""
    runtime = ContextRuntime()
    msgs = [{"role": "user", "content": "x" * 400}]  # 400 chars → 100 tokens
    assert runtime.should_auto_compact(msgs, token_limit=50) is True
    assert runtime.should_auto_compact(msgs, token_limit=200) is False


@pytest.mark.asyncio
async def test_context_runtime_with_real_compressor_reduces_messages():
    """When llm_call_fn is injected, compress_messages() delegates to
    ContextCompressor and actually reduces message count."""
    from unittest.mock import AsyncMock

    # A fake LLM that returns a summary string
    fake_llm = AsyncMock(return_value="[Compressed summary of conversation]")

    # Use a moderate context limit so tail budget < total messages
    runtime = ContextRuntime(
        llm_call_fn=fake_llm,
        context_limit_chars=50000,
    )

    # Build LARGE messages with substantial content to exceed tail budget
    messages: list[dict] = []
    for i in range(40):
        messages.append({
            "role": "user",
            "content": f"message {i:02d}: " + "x" * 250,
        })
        messages.append({
            "role": "assistant",
            "content": f"response {i:02d}: " + "y" * 250,
        })

    compressed = await runtime.compress_messages(
        messages, model="test-model", session_id="test-session",
    )

    # Should have called the LLM for summary
    fake_llm.assert_awaited_once()
    # Should be fewer messages than original
    assert len(compressed) < len(messages), (
        f"Expected compressed < original, got {len(compressed)} >= {len(messages)}"
    )
    # Should contain the summary content
    assert any(
        "summary" in str(m.get("content", "")).lower() for m in compressed
    ), f"Compressed output should contain summary: {compressed}"


def test_context_runtime_no_compressor_is_explicit_no_op():
    """Without llm_call_fn, compress_messages() returns messages unchanged
    but behavior is explicit, not accidental."""
    runtime = ContextRuntime()  # no llm_call_fn

    # _compressor should be None
    assert runtime._compressor is None
