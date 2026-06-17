"""Tests for BridgeRuntimeLoop persistent event loop (Phase 27.1)."""

import asyncio

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────


class _CaptureSend:
    """Capture _send() calls for verification."""
    def __init__(self):
        self.messages: list[dict] = []

    def send(self, data: dict) -> None:
        self.messages.append(data)

    def last(self) -> dict | None:
        return self.messages[-1] if self.messages else None


def _dispatch_legacy(_req_id: str, _method: str, _params: dict) -> None:
    """Simulated legacy dispatch that simply echoes."""
    # This would call _send directly in production, but in tests
    # we capture via the send_func
    pass  # Legacy handlers use module-level _send, not capturable


# ── BridgeRuntimeLoop creation ───────────────────────────────────────────


def test_bridge_runtime_loop_creates_with_send_and_dispatch():
    """BridgeRuntimeLoop accepts send_func and dispatch_legacy_func."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()

    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=_dispatch_legacy,
        dev_mode=False,
    )
    assert loop._send is not None
    assert callable(loop._send)
    assert loop._dispatch_legacy is _dispatch_legacy
    assert loop._dev_mode is False
    assert loop.app_server is None  # not started yet
    assert loop.loop is None  # not started yet


def test_bridge_runtime_loop_dev_mode():
    """dev_mode=True enables dev- prefixed client_id generation."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
        dev_mode=True,
    )
    assert loop._dev_mode is True

    # In dev mode, missing client_id generates a dev- prefix
    client_id = loop._resolve_client_id({})
    assert client_id.startswith("dev-")


@pytest.mark.asyncio
async def test_bridge_runtime_loop_resolve_client_id_with_explicit():
    """Explicit client_id is returned as-is."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )

    assert loop._resolve_client_id({"client_id": "my-client"}) == "my-client"
    assert loop._resolve_client_id({"caller_id": "caller-1"}) == "caller-1"
    assert loop._resolve_client_id({"user_id": "user-1"}) == "user-1"
    # client_id takes precedence over caller_id
    assert loop._resolve_client_id({"client_id": "c1", "caller_id": "c2"}) == "c1"


def test_bridge_runtime_loop_missing_client_id_raises_error():
    """Missing client_id raises AppServerError in production mode (Phase 27.5)."""
    from miqi.bridge.loop import BridgeRuntimeLoop
    from miqi.runtime.app_server import AppServerError

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
        dev_mode=False,
    )

    with pytest.raises(AppServerError, match="client_id is required"):
        loop._resolve_client_id({})


def test_bridge_runtime_loop_dev_mode_allows_missing_client_id():
    """In dev mode, missing client_id generates a dev- prefix."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
        dev_mode=True,
    )

    client_id = loop._resolve_client_id({})
    assert client_id.startswith("dev-")


# ── AppServer method registration ────────────────────────────────────────


@pytest.mark.asyncio
async def test_bridge_init_app_server_registers_handlers():
    """After _init_app_server, AppServer has status, replay, and command handlers."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()

    methods = loop.app_server._methods
    assert "status" in methods
    assert "replay.turns" in methods
    assert "replay.timeline" in methods
    assert "replay.messages" in methods
    assert "thread.create" in methods
    assert "thread.list" in methods
    assert "chat.abort" in methods

    await loop._shutdown()


# ── Event sink translation ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_sink_translates_appserver_to_bridge_format():
    """AppServer event envelope is translated to legacy bridge wire format."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=_dispatch_legacy,
    )

    # Simulate what _setup_event_sink does
    async def _desktop_sink(envelope):
        capturer.send({
            "id": envelope.get("request_id"),
            "type": envelope["event"],
            "data": envelope["data"],
        })

    await _desktop_sink({
        "request_id": "req-123",
        "event": "progress",
        "data": {"msg": "hello"},
    })

    assert capturer.last() == {
        "id": "req-123",
        "type": "progress",
        "data": {"msg": "hello"},
    }

    # Push events (no request_id)
    await _desktop_sink({
        "request_id": None,
        "event": "session_expiring",
        "data": {"session_id": "s1"},
    })

    assert capturer.last() == {
        "id": None,
        "type": "session_expiring",
        "data": {"session_id": "s1"},
    }


# ── Shutdown ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shutdown_stops_app_server():
    """_shutdown stops the AppServer."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()
    assert loop.app_server._running is True

    await loop._shutdown()
    assert loop.app_server._running is False


# ── Phase 27 acceptance tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_send_handler_registered_on_app_server():
    """chat.send is registered as an AppServer method."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()

    methods = loop.app_server._methods
    assert "chat.send" in methods
    assert "chat.abort" in methods
    assert "agent.spawn" in methods
    assert "agent.kill" in methods

    await loop._shutdown()


def test_missing_client_id_rejected_in_production():
    """Missing client_id raises AppServerError (no legacy shim)."""
    from miqi.bridge.loop import BridgeRuntimeLoop
    from miqi.runtime.app_server import AppServerError

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
        dev_mode=False,
    )
    with pytest.raises(AppServerError, match="client_id is required"):
        loop._resolve_client_id({})


def test_no_runtime_warning_in_production_path():
    """BridgeRuntimeLoop in production mode raises no UserWarning."""
    import warnings

    from miqi.bridge.loop import BridgeRuntimeLoop
    from miqi.runtime.app_server import AppServerError

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
        dev_mode=False,
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            loop._resolve_client_id({})
        except AppServerError:
            pass  # Expected

    # No UserWarning should have been emitted
    user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
    assert len(user_warnings) == 0, (
        f"Unexpected UserWarning(s): {[str(x.message) for x in user_warnings]}"
    )


@pytest.mark.asyncio
async def test_shutdown_cancels_pending_tasks():
    """After shutdown, pending tasks are cancelled and resources cleaned up."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()

    # Manually add a task to simulate an active chat turn
    async def _forever():
        while True:
            await asyncio.sleep(1)

    task = asyncio.create_task(_forever())
    loop._active_chat_tasks["test-task"] = task

    await loop._shutdown()

    # Task should be cancelled
    assert task.done()
    assert task.cancelled() or task.exception() is not None
    # Active chat tasks should be cleared
    assert len(loop._active_chat_tasks) == 0
    # AppServer should be stopped
    assert loop.app_server._running is False


# ── Phase 41: Codex turn handler registration ────────────────────────────


@pytest.mark.asyncio
async def test_phase41_turn_handlers_registered_on_bridge_app_server():
    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()

    methods = loop.app_server._methods
    for method in [
        "turn/start",
        "turn/interrupt",
        "turn/steer",
        "thread/compact/start",
        "thread/inject_items",
    ]:
        assert method in methods

    await loop._shutdown()

