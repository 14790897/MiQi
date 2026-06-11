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

        async def replace_messages_with_compaction(self, thread_id, turn_id, replacement):
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
