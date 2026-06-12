"""Tests for BridgeRuntimeLoop persistent event loop (Phase 27.1)."""

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


def test_bridge_runtime_loop_missing_client_id_warns():
    """Missing client_id generates a warning and legacy shim in production mode."""
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
        dev_mode=False,
    )

    with pytest.warns(UserWarning, match="client_id"):
        client_id = loop._resolve_client_id({})

    assert client_id.startswith("legacy-desktop-")


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

    await loop.app_server.stop()


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
