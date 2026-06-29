"""Tests for streaming delta and tool lifecycle ledger recording (Phase 24.4)."""

import pytest


@pytest.mark.asyncio
async def test_streaming_deltas_are_recorded_in_ledger(fake_config, tmp_path):
    from miqi.providers.base import LLMResponse, LLMStreamEvent
    from miqi.protocol.commands import UserMessage
    from miqi.protocol.events import TurnCompleteEvent
    from miqi.runtime.session import RuntimeSession

    class Provider:
        def get_default_model(self):
            return "test-model"

        async def chat(self, **kwargs):
            return LLMResponse(content="hello", finish_reason="stop")

        async def stream_chat(self, **kwargs):
            yield LLMStreamEvent(kind="content_delta", delta="hel")
            yield LLMStreamEvent(kind="content_delta", delta="lo")
            yield LLMStreamEvent(
                kind="completed",
                response=LLMResponse(content="hello", finish_reason="stop"),
            )

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=Provider(),
        session_id="sess-ledger-delta",
        workspace=tmp_path,
    )
    await runtime.start()
    try:
        await runtime.submit(UserMessage(content="hi", thread_id="thread-delta"))
        while True:
            event = await runtime.next_event(timeout=2)
            if isinstance(event, TurnCompleteEvent):
                break

        items = await runtime.services.ledger_runtime.load_items("thread-delta")
        deltas = [item for item in items if item.item_type == "assistant_delta"]

        assert [item.content for item in deltas] == ["hel", "lo"]
        assert [item.payload["index"] for item in deltas] == [0, 1]
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_tool_calls_are_recorded_in_ledger(fake_config, tmp_path):
    from miqi.providers.base import LLMResponse, LLMStreamEvent, ToolCallRequest
    from miqi.protocol.commands import UserMessage
    from miqi.protocol.events import TurnCompleteEvent
    from miqi.runtime.session import RuntimeSession

    class Provider:
        def __init__(self):
            self.calls = 0

        def get_default_model(self):
            return "test-model"

        async def chat(self, **kwargs):
            return LLMResponse(content="done", finish_reason="stop")

        async def stream_chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield LLMStreamEvent(
                    kind="completed",
                    response=LLMResponse(
                        content="",
                        finish_reason="tool_calls",
                        tool_calls=[
                            ToolCallRequest(
                                id="call-1",
                                name="read_file",
                                arguments={"path": "missing.txt"},
                            )
                        ],
                    ),
                )
            else:
                yield LLMStreamEvent(
                    kind="completed",
                    response=LLMResponse(content="done", finish_reason="stop"),
                )

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=Provider(),
        session_id="sess-ledger-tools",
        workspace=tmp_path,
    )
    await runtime.start()
    try:
        await runtime.submit(UserMessage(content="read file", thread_id="thread-tools"))
        while True:
            event = await runtime.next_event(timeout=2)
            if isinstance(event, TurnCompleteEvent):
                break

        items = await runtime.services.ledger_runtime.load_items("thread-tools")
        types = [item.item_type for item in items]

        assert "tool_call_started" in types
        assert "tool_call_completed" in types
    finally:
        await runtime.stop()
