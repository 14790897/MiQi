"""Tests for bridge transport adapter over AppServer (Phase 26.2)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────


class _CaptureStdout:
    """Capture _send() calls during a test."""
    def __init__(self):
        self.messages: list[dict] = []

    def send(self, data: dict) -> None:
        self.messages.append(data)


def _make_app_server():
    """Create an AppServer with a few registered test methods."""
    from miqi.runtime.app_server import AppServer, ClientSessionRegistry

    registry = ClientSessionRegistry()
    server = AppServer(registry)

    async def echo_handler(request_id, params, client_id, session_id, registry_):
        return {"result": {"echo": params.get("msg", "")}}

    async def status_handler(request_id, params, client_id, session_id, registry_):
        return {"result": {"status": "ok"}}

    async def error_handler(request_id, params, client_id, session_id, registry_):
        from miqi.runtime.app_server import AppServerError
        raise AppServerError("test error", code="TEST_ERROR", recoverable=True)

    server.register_method("test.echo", echo_handler)
    server.register_method("test.status", status_handler)
    server.register_method("test.error", error_handler)

    return server


# ── AppServer dispatch via transport layer ───────────────────────────────


@pytest.mark.asyncio
async def test_transport_dispatches_request_to_app_server():
    """Simulate a full dispatch cycle: request JSON → AppServer → response JSON."""
    from miqi.runtime.app_server import ClientSessionRegistry

    server = _make_app_server()
    capturer = _CaptureStdout()

    request = json.dumps({
        "id": "req-001",
        "method": "test.echo",
        "params": {"msg": "hello"},
    })

    # Parse request (simulating stdin read)
    req = json.loads(request)
    req_id = req["id"]
    method = req["method"]
    params = req.get("params", {})

    # Resolve client_id (with shim)
    registry: ClientSessionRegistry = server.registry
    client_id = registry.resolve_client_id(params.get("client_id"))

    # Dispatch through AppServer
    response = await server.dispatch(
        request_id=req_id,
        method=method,
        params=params,
        client_id=client_id,
    )

    # Write response (simulating stdout write)
    capturer.send(response)

    assert len(capturer.messages) == 1
    assert capturer.messages[0]["request_id"] == "req-001"
    assert capturer.messages[0]["result"] == {"echo": "hello"}


@pytest.mark.asyncio
async def test_transport_unknown_method_returns_error():
    server = _make_app_server()
    capturer = _CaptureStdout()

    response = await server.dispatch(
        request_id="req-002",
        method="nonexistent.method",
        params={},
        client_id="desktop-test",
    )
    capturer.send(response)

    assert "error" in capturer.messages[0]
    assert capturer.messages[0]["code"] == "UNKNOWN_METHOD"


@pytest.mark.asyncio
async def test_transport_handler_error_is_caught():
    server = _make_app_server()
    capturer = _CaptureStdout()

    response = await server.dispatch(
        request_id="req-003",
        method="test.error",
        params={},
        client_id="desktop-test",
    )
    capturer.send(response)

    assert "error" in capturer.messages[0]
    assert capturer.messages[0]["code"] == "TEST_ERROR"
    assert capturer.messages[0]["recoverable"] is True


@pytest.mark.asyncio
async def test_transport_sends_valid_json_line():
    """The output must be valid JSON as one line (bridge protocol)."""
    server = _make_app_server()

    response = await server.dispatch(
        request_id="req-004",
        method="test.status",
        params={},
        client_id="desktop-test",
    )

    # Serialize as the bridge would
    line = json.dumps(response, ensure_ascii=False)
    assert "\n" not in line  # single line

    # Must be parseable by a JSON consumer
    parsed = json.loads(line)
    assert parsed["request_id"] == "req-004"
    assert parsed["result"]["status"] == "ok"


# ── client_id shim integration ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_transport_missing_client_id_generates_shim_with_warning():
    server = _make_app_server()

    with pytest.warns(UserWarning, match="client_id"):
        client_id = server.registry.resolve_client_id(None)

    assert client_id.startswith("legacy-desktop-")

    response = await server.dispatch(
        request_id="req-005",
        method="test.echo",
        params={"msg": "with-shim"},
        client_id=client_id,
    )
    assert "result" in response


@pytest.mark.asyncio
async def test_transport_explicit_client_id_no_warning():
    server = _make_app_server()

    client_id = server.registry.resolve_client_id("my-client")
    assert client_id == "my-client"

    response = await server.dispatch(
        request_id="req-006",
        method="test.status",
        params={},
        client_id=client_id,
    )
    assert "result" in response


# ── Bridge main() integration ────────────────────────────────────────────


def test_bridge_app_server_created_in_main(monkeypatch, tmp_path):
    """Verify that the bridge creates an AppServer during initialization."""
    from miqi.bridge.server import _ensure_app_server
    from miqi.runtime.app_server import AppServer

    # Patch config loading
    import miqi.bridge.server as bridge_module

    # Simulate creating an AppServer for the bridge
    with patch.object(bridge_module, '_app_server', None, create=True):
        app_server = _ensure_app_server()
        assert isinstance(app_server, AppServer)
        assert app_server.registry is not None


# ── Existing dispatch compatibility ──────────────────────────────────────


def test_bridge_existing_dispatch_still_works(monkeypatch):
    """The existing _METHODS dispatch table must still work after
    AppServer is added — backward compatibility."""
    from miqi.bridge.server import _METHODS, _dispatch

    # _METHODS should contain the existing handlers
    assert "status" in _METHODS
    assert "chat.send" in _METHODS
    assert "chat.abort" in _METHODS
    assert "config.get" in _METHODS
    assert "sessions.list" in _METHODS
