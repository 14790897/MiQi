"""Phase 5 tests — ModelClient adapter and FakeModelClient."""

from __future__ import annotations

import pytest

from miqi.kun_runtime.model_client import (
    FakeModelClient,
    MiQiModelClient,
    ModelRequest,
    ModelToolSpec,
    _build_messages,
    _build_tools,
    _item_to_message,
)
from miqi.providers.base import LLMProvider, LLMResponse, ToolCallRequest

# ═══════════════════════════════════════════════════════════════════════════════
# FakeModelClient tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFakeModelClient:
    @pytest.mark.asyncio
    async def test_no_tools_text_only(self) -> None:
        client = FakeModelClient(text_chunks=["Hello, world!"])
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        kinds = [c.kind for c in chunks]
        assert "assistant_text_delta" in kinds
        assert "completed" in kinds
        assert chunks[-1].stopReason == "stop"

    @pytest.mark.asyncio
    async def test_with_tool_calls(self) -> None:
        client = FakeModelClient(
            text_chunks=["Let me check..."],
            tool_calls=[{"id": "call_1", "name": "read", "arguments": {"path": "test.txt"}}],
        )
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        kinds = [c.kind for c in chunks]
        assert "tool_call_complete" in kinds
        assert chunks[-1].stopReason == "tool_calls"

    @pytest.mark.asyncio
    async def test_with_reasoning(self) -> None:
        client = FakeModelClient(
            reasoning_chunks=["Let me think..."],
            text_chunks=["Answer"],
        )
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        kinds = [c.kind for c in chunks]
        assert "assistant_reasoning_delta" in kinds
        assert "assistant_text_delta" in kinds

    @pytest.mark.asyncio
    async def test_with_usage(self) -> None:
        client = FakeModelClient(
            text_chunks=["Done"],
            usage={"promptTokens": 100, "completionTokens": 50, "totalTokens": 150},
        )
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        usage_chunks = [c for c in chunks if c.kind == "usage"]
        assert len(usage_chunks) == 1
        assert usage_chunks[0].usage == {"promptTokens": 100, "completionTokens": 50, "totalTokens": 150}

    @pytest.mark.asyncio
    async def test_error(self) -> None:
        client = FakeModelClient(error="provider down", error_code="API_ERROR")
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        assert len(chunks) == 1
        assert chunks[0].kind == "error"
        assert chunks[0].message == "provider down"

    @pytest.mark.asyncio
    async def test_records_requests(self) -> None:
        client = FakeModelClient(text_chunks=["OK"])
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake", temperature=0.1)
        async for _ in client.stream(req):
            pass
        assert len(client._requests) == 1
        assert client._requests[0].thread_id == "th1"

    @pytest.mark.asyncio
    async def test_multiple_text_chunks(self) -> None:
        client = FakeModelClient(text_chunks=["Part 1 ", "Part 2 ", "Part 3"])
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        text_chunks = [c.text for c in chunks if c.kind == "assistant_text_delta"]
        assert text_chunks == ["Part 1 ", "Part 2 ", "Part 3"]


# ═══════════════════════════════════════════════════════════════════════════════
# Message conversion tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMessageConversion:
    def test_user_message_item(self) -> None:
        item = {"id": "u1", "kind": "user_message", "text": "hello"}
        msg = _item_to_message(item)
        assert msg is not None
        assert msg["role"] == "user"
        assert msg["content"] == "hello"

    def test_assistant_text_item(self) -> None:
        item = {"id": "a1", "kind": "assistant_text", "text": "response"}
        msg = _item_to_message(item)
        assert msg is not None
        assert msg["role"] == "assistant"
        assert msg["content"] == "response"

    def test_tool_call_item(self) -> None:
        item = {
            "id": "tc1", "kind": "tool_call",
            "toolName": "read", "callId": "call_1",
            "arguments": {"path": "test.txt"},
        }
        msg = _item_to_message(item)
        assert msg is not None
        assert msg["role"] == "assistant"
        assert msg["tool_calls"][0]["function"]["name"] == "read"

    def test_tool_result_item(self) -> None:
        item = {
            "id": "tr1", "kind": "tool_result",
            "toolName": "read", "callId": "call_1",
            "output": "file content",
        }
        msg = _item_to_message(item)
        assert msg is not None
        assert msg["role"] == "tool"
        assert msg["content"] == "file content"

    def test_error_item(self) -> None:
        item = {"id": "e1", "kind": "error", "message": "something failed"}
        msg = _item_to_message(item)
        assert msg is not None
        assert msg["role"] == "system"
        assert "failed" in msg["content"]

    def test_compaction_item(self) -> None:
        item = {"id": "c1", "kind": "compaction", "summary": "Earlier conversation"}
        msg = _item_to_message(item)
        assert msg is not None
        assert msg["role"] == "system"
        assert msg["content"] == "Earlier conversation"


class TestBuildMessages:
    def test_empty_request(self) -> None:
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        msgs = _build_messages(req)
        assert msgs == []

    def test_system_prompt(self) -> None:
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake", system_prompt="You are helpful.")
        msgs = _build_messages(req)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "system"

    def test_context_instructions(self) -> None:
        req = ModelRequest(
            thread_id="th1", turn_id="t1", model="fake",
            system_prompt="You are helpful.",
            context_instructions=["Skill: code-review"],
        )
        msgs = _build_messages(req)
        assert len(msgs) == 1
        assert "Skill: code-review" in msgs[0]["content"]

    def test_history_items(self) -> None:
        req = ModelRequest(
            thread_id="th1", turn_id="t1", model="fake",
            history=[
                {"id": "u1", "kind": "user_message", "text": "hello"},
                {"id": "a1", "kind": "assistant_text", "text": "hi"},
            ],
        )
        msgs = _build_messages(req)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_mode_instruction(self) -> None:
        req = ModelRequest(
            thread_id="th1", turn_id="t1", model="fake",
            system_prompt="Base prompt",
            mode_instruction="Plan mode enabled.",
        )
        msgs = _build_messages(req)
        assert "Plan mode enabled" in msgs[0]["content"]


class TestBuildTools:
    def test_converts_tool_specs(self) -> None:
        specs = [
            ModelToolSpec(
                name="read",
                description="Read a file",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            ),
        ]
        result = _build_tools(specs)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read"

    def test_empty_tools(self) -> None:
        assert _build_tools([]) == []


# ═══════════════════════════════════════════════════════════════════════════════
# MiQiModelClient integration test (pseudo-streaming with FakeProvider)
# ═══════════════════════════════════════════════════════════════════════════════


class FakeProvider(LLMProvider):
    """A provider that returns configurable responses."""

    def __init__(
        self,
        content: str = "",
        reasoning: str | None = None,
        tool_calls: list[dict] | None = None,
        usage: dict | None = None,
        finish_reason: str = "stop",
        raise_error: Exception | None = None,
    ):
        super().__init__()
        self._content = content
        self._reasoning = reasoning
        self._raw_tool_calls = tool_calls or []
        self._usage = usage
        self._finish_reason = finish_reason
        self._raise_error = raise_error

    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):
        if self._raise_error:
            raise self._raise_error
        return LLMResponse(
            content=self._content,
            tool_calls=[ToolCallRequest(**tc) for tc in self._raw_tool_calls],
            finish_reason=self._finish_reason,
            usage=self._usage or {},
            reasoning_content=self._reasoning,
        )

    def get_default_model(self) -> str:
        return "fake-model"


class TestMiQiModelClient:
    @pytest.mark.asyncio
    async def test_text_only(self) -> None:
        provider = FakeProvider(content="Hello from MiQi!")
        client = MiQiModelClient(provider)
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        kinds = [c.kind for c in chunks]
        assert "assistant_text_delta" in kinds
        assert "completed" in kinds
        text = next(c.text for c in chunks if c.kind == "assistant_text_delta")
        assert text == "Hello from MiQi!"

    @pytest.mark.asyncio
    async def test_with_reasoning(self) -> None:
        provider = FakeProvider(content="Answer", reasoning="Hmm...")
        client = MiQiModelClient(provider)
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        reasoning = [c for c in chunks if c.kind == "assistant_reasoning_delta"]
        assert len(reasoning) == 1
        assert reasoning[0].text == "Hmm..."

    @pytest.mark.asyncio
    async def test_with_tool_calls(self) -> None:
        provider = FakeProvider(
            content="Let me read that.",
            tool_calls=[{"id": "call_1", "name": "read", "arguments": {"path": "a.txt"}}],
        )
        client = MiQiModelClient(provider)
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        tc_chunks = [c for c in chunks if c.kind == "tool_call_complete"]
        assert len(tc_chunks) == 1
        assert tc_chunks[0].toolName == "read"
        complete = [c for c in chunks if c.kind == "completed"]
        assert complete[0].stopReason == "tool_calls"

    @pytest.mark.asyncio
    async def test_with_usage(self) -> None:
        provider = FakeProvider(
            content="Done",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        client = MiQiModelClient(provider)
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        usage = [c for c in chunks if c.kind == "usage"]
        assert len(usage) == 1
        assert usage[0].usage["promptTokens"] == 100

    @pytest.mark.asyncio
    async def test_provider_error(self) -> None:
        provider = FakeProvider(raise_error=RuntimeError("connection refused"))
        client = MiQiModelClient(provider)
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        assert len(chunks) == 1
        assert chunks[0].kind == "error"
        assert "connection refused" in chunks[0].message

    @pytest.mark.asyncio
    async def test_api_error_finish_reason(self) -> None:
        provider = FakeProvider(content="API Error", finish_reason="error")
        client = MiQiModelClient(provider)
        req = ModelRequest(thread_id="th1", turn_id="t1", model="fake")
        chunks = [c async for c in client.stream(req)]
        assert chunks[0].kind == "error"

    @pytest.mark.asyncio
    async def test_passes_tools_to_provider(self) -> None:
        provider = FakeProvider(content="OK")
        client = MiQiModelClient(provider)
        req = ModelRequest(
            thread_id="th1", turn_id="t1", model="fake",
            tools=[ModelToolSpec(name="read", description="Read file", input_schema={"type": "object"})],
        )
        chunks = [c async for c in client.stream(req)]
        kinds = [c.kind for c in chunks]
        assert "completed" in kinds  # didn't crash, provider handled the tools arg
