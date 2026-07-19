# ruff: noqa: N815  # camelCase field names match KUN wire format
"""Model client adapter for KUN runtime.

Wraps MiQi ``LLMProvider.chat()`` to produce KUN ``ModelStreamChunk``
values via an async generator.

Phase 5a: pseudo-streaming — the full provider response is yielded as a
single ``assistant_text_delta`` chunk.
Phase 5b: real streaming for OpenAI/DeepSeek-compatible providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from miqi.providers.base import LLMProvider

# ═══════════════════════════════════════════════════════════════════════════════
# Model stream chunk types
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ModelStreamChunk:
    """A single streaming chunk from a model response.

    Matches KUN ``ModelStreamChunk`` union type.
    """
    kind: str  # assistant_text_delta, assistant_reasoning_delta, tool_call_delta,
               # tool_call_complete, usage, completed, error
    text: str | None = None
    callId: str | None = None
    toolName: str | None = None
    arguments: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    stopReason: str | None = None
    message: str | None = None
    code: str | None = None


@dataclass
class ModelToolSpec:
    """Tool specification sent to the model provider."""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    tool_kind: str | None = None


@dataclass
class ModelRequest:
    """A complete model turn request.

    Matches KUN ``ModelRequest`` interface.
    """
    thread_id: str
    turn_id: str
    model: str
    system_prompt: str | None = None
    mode_instruction: str | None = None
    context_instructions: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    tools: list[ModelToolSpec] = field(default_factory=list)
    max_tokens: int | None = None
    temperature: float = 0.7
    reasoning_effort: str | None = None
    abort_signal: Any = None  # placeholder for CancellationToken in Phase 5b


# ═══════════════════════════════════════════════════════════════════════════════
# MiQiModelClient — wraps LLMProvider
# ═══════════════════════════════════════════════════════════════════════════════


class MiQiModelClient:
    """KUN-compatible model client backed by a MiQi LLMProvider.

    Phase 5a: pseudo-streaming — the full provider response is yielded as
    individual chunks after the ``chat()`` call completes.

    Usage::

        client = MiQiModelClient(provider)
        async for chunk in client.stream(request):
            if chunk.kind == "assistant_text_delta":
                print(chunk.text)
    """

    def __init__(self, provider: LLMProvider):
        self._provider = provider
        self.model = provider.get_default_model()

    @property
    def provider_name(self) -> str:
        return type(self._provider).__name__

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamChunk]:
        """Execute the model request and yield streaming chunks.

        Pseudo-streaming (Phase 5a):
        1. Build provider-compatible messages from the request.
        2. Call ``provider.chat()``.
        3. Yield ``assistant_reasoning_delta`` if reasoning_content present.
        4. Yield ``assistant_text_delta`` with full content.
        5. Yield ``tool_call_complete`` for each tool call.
        6. Yield ``usage``.
        7. Yield ``completed``.
        """
        # Build messages
        messages = _build_messages(request)

        # Phase 56: hard-trim messages before provider call so we never
        # send a request that exceeds the model's input token limit.
        from miqi.kun_runtime.context_estimator import (
            estimate_tokens,
            get_safe_context_limit,
        )
        model = request.model or self.model
        safe_limit = get_safe_context_limit(model)
        est = estimate_tokens(str(messages))
        if est > safe_limit:
            logger.warning(
                "KUN pre-send guard: estimated {} tokens exceeds {} limit "
                "for {}; trimming oldest pairs",
                est, safe_limit, model,
            )
            head_protect = 1 if messages and messages[0].get("role") == "system" else 0
            while len(messages) > head_protect + 1 and est > safe_limit:
                head_protect = 1 if messages and messages[0].get("role") == "system" else 0
                for i in range(head_protect, len(messages) - 1):
                    if messages[i].get("role") in ("assistant", "tool"):
                        messages.pop(i)
                        break
                else:
                    break
                est = estimate_tokens(str(messages))
            logger.info(
                "KUN pre-send guard: est tokens now {}", est,
            )

        # Build tools
        tools = _build_tools(request.tools) if request.tools else None

        # Call provider
        try:
            response = await self._provider.chat(
                messages=messages,
                tools=tools,
                model=request.model or self.model,
                max_tokens=request.max_tokens or 8192,
                temperature=request.temperature,
            )
        except Exception as exc:
            yield ModelStreamChunk(
                kind="error",
                message=str(exc),
                code="provider_error",
            )
            return

        # Check for API error
        if response.finish_reason == "error":
            yield ModelStreamChunk(
                kind="error",
                message=response.content or "Provider returned an error",
                code="api_error",
            )
            return

        # Yield reasoning delta if present
        if response.reasoning_content:
            yield ModelStreamChunk(
                kind="assistant_reasoning_delta",
                text=response.reasoning_content,
            )

        # Yield text delta
        if response.content:
            yield ModelStreamChunk(
                kind="assistant_text_delta",
                text=response.content,
            )

        # Yield tool calls
        for tc in response.tool_calls:
            yield ModelStreamChunk(
                kind="tool_call_complete",
                callId=tc.id,
                toolName=tc.name,
                arguments=tc.arguments,
            )

        # Yield usage
        if response.usage:
            usage = {
                "promptTokens": response.usage.get("prompt_tokens", 0),
                "completionTokens": response.usage.get("completion_tokens", 0),
                "totalTokens": response.usage.get("total_tokens", 0),
            }
            yield ModelStreamChunk(
                kind="usage",
                usage=usage,
            )

        # Yield completed
        stop_reason = "tool_calls" if response.has_tool_calls else "stop"
        yield ModelStreamChunk(
            kind="completed",
            stopReason=stop_reason,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# FakeModelClient — for testing without real API calls
# ═══════════════════════════════════════════════════════════════════════════════


class FakeModelClient:
    """A test-double model client that yields configurable chunks.

    Usage::

        client = FakeModelClient(text_chunks=["Hello, "], tool_calls=[...])
        async for chunk in client.stream(request):
            ...
    """

    def __init__(
        self,
        text_chunks: list[str] | None = None,
        reasoning_chunks: list[str] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        error: str | None = None,
        error_code: str | None = None,
    ):
        self.text_chunks = text_chunks or []
        self.reasoning_chunks = reasoning_chunks or []
        self.tool_calls = tool_calls or []
        self._usage = usage
        self._error = error
        self._error_code = error_code
        self.model = "fake-model"
        self.provider_name = "FakeModelClient"
        self._requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamChunk]:
        self._requests.append(request)
        if self._error:
            yield ModelStreamChunk(kind="error", message=self._error, code=self._error_code)
            return
        for text in self.reasoning_chunks:
            yield ModelStreamChunk(kind="assistant_reasoning_delta", text=text)
        for text in self.text_chunks:
            yield ModelStreamChunk(kind="assistant_text_delta", text=text)
        for tc in self.tool_calls:
            yield ModelStreamChunk(
                kind="tool_call_complete",
                callId=tc.get("id", "call_1"),
                toolName=tc.get("name", "unknown"),
                arguments=tc.get("arguments", {}),
            )
        if self._usage:
            yield ModelStreamChunk(kind="usage", usage=self._usage)
        yield ModelStreamChunk(
            kind="completed",
            stopReason="tool_calls" if self.tool_calls else "stop",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _build_messages(request: ModelRequest) -> list[dict[str, Any]]:
    """Convert a KUN ModelRequest into provider-compatible messages."""
    messages: list[dict[str, Any]] = []

    # System prompt
    system_parts: list[str] = []
    if request.system_prompt:
        system_parts.append(request.system_prompt)
    if request.mode_instruction:
        system_parts.append(request.mode_instruction)
    for instruction in request.context_instructions:
        system_parts.append(instruction)
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # History items — convert TurnItems to message dicts
    for item in request.history:
        msg = _item_to_message(item)
        if msg:
            messages.append(msg)

    return messages


def _item_to_message(item: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a KUN TurnItem dict to a provider message dict."""
    kind = item.get("kind", "")
    item.get("role", "")

    if kind == "user_message":
        return {"role": "user", "content": item.get("text", "")}
    elif kind == "assistant_text":
        msg: dict[str, Any] = {"role": "assistant", "content": item.get("text", "")}
        return msg
    elif kind == "assistant_reasoning":
        return {"role": "assistant", "content": item.get("text", ""),
                "reasoning_content": item.get("text", "")}
    elif kind == "tool_call":
        return {
            "role": "assistant",
            "content": item.get("summary") or None,
            "tool_calls": [{
                "id": item.get("callId", ""),
                "type": "function",
                "function": {
                    "name": item.get("toolName", ""),
                    "arguments": item.get("arguments", {}),
                },
            }],
        }
    elif kind == "tool_result":
        return {
            "role": "tool",
            "tool_call_id": item.get("callId", ""),
            "name": item.get("toolName", ""),
            "content": item.get("output", ""),
        }
    elif kind == "error":
        return {"role": "system", "content": f"Error: {item.get('message', '')}"}
    elif kind == "compaction":
        return {"role": "system", "content": item.get("summary", "")}
    return None


def _build_tools(tool_specs: list[ModelToolSpec]) -> list[dict[str, Any]]:
    """Convert KUN ModelToolSpec list to OpenAI-format tool definitions."""
    tools = []
    for spec in tool_specs:
        tools.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.input_schema,
            },
        })
    return tools
