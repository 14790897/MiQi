"""End-to-end tests for turn/start event projection through RuntimeSession."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.turn_app_handlers import register_codex_turn_handlers


@pytest.mark.asyncio
async def test_turn_start_streams_codex_item_events(tmp_path, fake_config):
    from miqi.providers.base import LLMResponse, LLMStreamEvent
    from miqi.runtime.session import RuntimeSession

    class Provider:
        def get_default_model(self):
            return "test-model"

        async def stream_chat(self, **kwargs):
            yield LLMStreamEvent(kind="content_delta", delta="hel")
            yield LLMStreamEvent(kind="content_delta", delta="lo")
            yield LLMStreamEvent(kind="completed", response=LLMResponse(
                content="hello",
                finish_reason="stop",
                usage={"total_tokens": 3},
            ))

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=Provider(),
        session_id="client-1:default",
        workspace=fake_config.workspace_path,
    )
    await runtime.start()

    registry = ClientSessionRegistry()
    registry._sessions[runtime.session_id] = runtime
    registry._client_sessions.setdefault("client-1", set()).add(runtime.session_id)
    registry._session_clients.setdefault(runtime.session_id, set()).add("client-1")
    registry._last_activity[runtime.session_id] = 0

    server = AppServer(registry)
    register_codex_turn_handlers(server)

    captured: list[dict] = []

    async def sink(envelope):
        captured.append(envelope)

    server.set_event_sink("client-1", sink)
    server.subscribe("client-1", runtime.session_id)

    response = await server.dispatch(
        "req-1",
        "turn/start",
        {
            "threadId": "thread-e2e",
            "clientUserMessageId": "client-msg-1",
            "input": [{"type": "text", "text": "hello"}],
        },
        "client-1",
        runtime.session_id,
    )

    assert response["result"]["turn"]["status"] == "inProgress"

    for _ in range(100):
        if any(e["event"] == "turn/completed" for e in captured):
            break
        await asyncio.sleep(0.01)

    events = [e["event"] for e in captured]
    assert "turn/started" in events
    assert "item/started" in events
    assert "item/agentMessage/delta" in events
    assert "item/completed" in events
    assert "thread/tokenUsage/updated" in events
    assert "turn/completed" in events

    completed = [e for e in captured if e["event"] == "turn/completed"][-1]
    assert completed["data"]["turn"]["status"] == "completed"

    await server.stop()


@pytest.mark.asyncio
async def test_turn_interrupt_streams_interrupted_completion(tmp_path, fake_config):
    import asyncio as _asyncio
    from miqi.providers.base import LLMResponse, LLMStreamEvent
    from miqi.runtime.session import RuntimeSession

    class Provider:
        def get_default_model(self):
            return "test-model"

        async def stream_chat(self, **kwargs):
            await _asyncio.sleep(30)
            yield LLMStreamEvent(kind="completed", response=LLMResponse(
                content="late",
                finish_reason="stop",
            ))

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=Provider(),
        session_id="client-1:default",
        workspace=fake_config.workspace_path,
    )
    await runtime.start()

    registry = ClientSessionRegistry()
    registry._sessions[runtime.session_id] = runtime
    registry._client_sessions.setdefault("client-1", set()).add(runtime.session_id)
    registry._session_clients.setdefault(runtime.session_id, set()).add("client-1")
    registry._last_activity[runtime.session_id] = 0

    server = AppServer(registry)
    register_codex_turn_handlers(server)
    captured: list[dict] = []

    async def sink(envelope):
        captured.append(envelope)

    server.set_event_sink("client-1", sink)
    server.subscribe("client-1", runtime.session_id)

    response = await server.dispatch(
        "req-1",
        "turn/start",
        {"threadId": "thread-interrupt", "input": [{"type": "text", "text": "wait"}]},
        "client-1",
        runtime.session_id,
    )
    turn_id = response["result"]["turn"]["id"]

    for _ in range(100):
        if runtime.active_turn_id("thread-interrupt") == turn_id:
            break
        await _asyncio.sleep(0.01)

    interrupt = await server.dispatch(
        "req-2",
        "turn/interrupt",
        {"threadId": "thread-interrupt", "turnId": turn_id},
        "client-1",
        runtime.session_id,
    )
    assert interrupt["result"] == {}

    for _ in range(100):
        if any(e["event"] == "turn/completed" for e in captured):
            break
        await _asyncio.sleep(0.01)

    completed = [e for e in captured if e["event"] == "turn/completed"][-1]
    assert completed["data"]["turn"]["status"] == "interrupted"

    await server.stop()
