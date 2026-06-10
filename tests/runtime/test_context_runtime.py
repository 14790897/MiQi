"""Tests for ContextRuntime (Phase 12.2)."""

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
