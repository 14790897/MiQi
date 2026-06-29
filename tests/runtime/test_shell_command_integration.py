"""Integration tests for thread/shellCommand through RuntimeSession."""

from __future__ import annotations

import asyncio

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry


def _register_runtime(registry, runtime):
    registry._sessions[runtime.session_id] = runtime
    registry._client_sessions.setdefault("client-1", set()).add(runtime.session_id)
    registry._session_clients.setdefault(runtime.session_id, set()).add("client-1")
    registry._last_activity[runtime.session_id] = 0


@pytest.mark.asyncio
async def test_thread_shell_command_standalone_streams_command_item(tmp_path, fake_config):
    from miqi.runtime.session import RuntimeSession
    from miqi.runtime.shell_command_app_handlers import register_shell_command_handlers

    class Provider:
        def get_default_model(self):
            return "test-model"

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=Provider(),
        session_id="client-1:default",
        workspace=fake_config.workspace_path,
    )
    await runtime.start()
    await runtime.services.thread_runtime.create_thread(
        thread_id="thread-shell",
        title="Shell Thread",
    )

    registry = ClientSessionRegistry()
    _register_runtime(registry, runtime)
    server = AppServer(registry)
    register_shell_command_handlers(server)
    captured: list[dict] = []

    async def sink(envelope):
        captured.append(envelope)

    server.set_event_sink("client-1", sink)
    server.subscribe("client-1", runtime.session_id)

    response = await server.dispatch(
        "req-1",
        "thread/shellCommand",
        {"threadId": "thread-shell", "command": "echo hello"},
        "client-1",
        runtime.session_id,
    )

    assert response["result"] == {}

    for _ in range(200):
        if any(e["event"] == "turn/completed" for e in captured):
            break
        await asyncio.sleep(0.01)

    events = [e["event"] for e in captured]
    assert "turn/started" in events
    assert "item/started" in events
    assert "item/completed" in events
    assert "turn/completed" in events

    command_items = [
        e["data"]["item"]
        for e in captured
        if e["event"] == "item/started"
        and e["data"]["item"]["type"] == "commandExecution"
    ]
    assert command_items
    assert command_items[0]["source"] == "userShell"

    await server.stop()


@pytest.mark.asyncio
async def test_thread_shell_command_ledger_records_user_shell_source(tmp_path, fake_config):
    from miqi.runtime.session import RuntimeSession
    from miqi.runtime.shell_command_app_handlers import register_shell_command_handlers

    class Provider:
        def get_default_model(self):
            return "test-model"

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=Provider(),
        session_id="client-1:default",
        workspace=fake_config.workspace_path,
    )
    await runtime.start()
    await runtime.services.thread_runtime.create_thread(
        thread_id="thread-shell-ledger",
        title="Shell Ledger Thread",
    )

    registry = ClientSessionRegistry()
    _register_runtime(registry, runtime)
    server = AppServer(registry)
    register_shell_command_handlers(server)

    response = await server.dispatch(
        "req-1",
        "thread/shellCommand",
        {"threadId": "thread-shell-ledger", "command": "echo ledger"},
        "client-1",
        runtime.session_id,
    )
    assert response["result"] == {}

    for _ in range(200):
        items = await runtime.services.ledger_runtime.load_items("thread-shell-ledger")
        if any(i.item_type == "turn_completed" for i in items):
            break
        await asyncio.sleep(0.01)

    items = await runtime.services.ledger_runtime.load_items("thread-shell-ledger")
    exec_started = [i for i in items if i.item_type == "exec_started"]
    assert exec_started
    assert exec_started[0].payload["source"] == "userShell"

    await server.stop()
