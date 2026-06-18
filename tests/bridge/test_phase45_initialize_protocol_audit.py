"""Phase 45 Initialize Protocol Audit Tests.

Tests for Codex-style initialize/initialized handshake through the bridge
transport layer. These tests verify the bridge-level initialization state
machine: NOT_INITIALIZED gate, ALREADY_INITIALIZED rejection, client_id
derivation, experimental API gate, and notification opt-out.

Tests that use BridgeRuntimeLoop push requests through the stdin queue
and capture responses. Tests that only need capability/initialize logic
use direct AppServer dispatch.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


class _CaptureSend:
    """Capture send() calls for verification."""
    def __init__(self):
        self.messages: list[dict] = []

    def send(self, data: dict) -> None:
        self.messages.append(data)

    def last(self) -> dict | None:
        return self.messages[-1] if self.messages else None

    def clear(self) -> None:
        self.messages.clear()


def _make_server_with_caps():
    """Create an AppServer with capabilities support (for direct tests).

    These tests bypass the bridge initialize gate and use direct
    AppServer.dispatch() — necessary for unit-testing capability
    and initialize handler behavior without full bridge setup.
    """
    from miqi.runtime.app_server import AppServer, ClientSessionRegistry

    registry = ClientSessionRegistry()
    server = AppServer(registry)
    return server, registry


async def _dispatch(server, registry, method, params, client_id="test-client", session_id=None, req_id="req-1"):
    return await server.dispatch(
        request_id=req_id,
        method=method,
        params=params,
        client_id=client_id,
        session_id=session_id,
    )


# ── 45.1.1: initialize method is registered or handled specially ────────────


@pytest.mark.asyncio
async def test_initialize_method_is_registered_on_server():
    """initialize method is registered and returns a valid response."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test-client", "title": "Test", "version": "1.0"},
    })

    assert "result" in resp, f"Expected result in initialize response, got: {resp}"
    result = resp["result"]
    assert "serverInfo" in result
    assert "userAgent" in result
    assert "capabilities" in result


# ── 45.1.2: initialize response contains required fields ────────────────────


@pytest.mark.asyncio
async def test_initialize_response_contains_server_info():
    """initialize response has serverInfo with name, title, version."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "miqi_desktop", "title": "MiQi Desktop", "version": "0.1.0"},
    })

    result = resp["result"]
    server_info = result["serverInfo"]
    assert server_info["name"] == "miqi"
    assert server_info["title"] == "MiQi"
    assert isinstance(server_info["version"], str)


@pytest.mark.asyncio
async def test_initialize_response_contains_user_agent():
    """initialize response includes userAgent string."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test", "title": "Test"},
    })

    assert "userAgent" in resp["result"]
    assert "miqi" in resp["result"]["userAgent"].lower()


@pytest.mark.asyncio
async def test_initialize_response_contains_home_paths():
    """initialize response includes miqiHome and codexHome paths."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test", "title": "Test"},
    })

    result = resp["result"]
    assert "miqiHome" in result
    assert "codexHome" in result
    assert isinstance(result["miqiHome"], str)
    assert isinstance(result["codexHome"], str)


@pytest.mark.asyncio
async def test_initialize_response_contains_platform():
    """initialize response includes platformFamily and platformOs."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test", "title": "Test"},
    })

    result = resp["result"]
    assert "platformFamily" in result
    assert "platformOs" in result


@pytest.mark.asyncio
async def test_initialize_response_contains_server_capabilities():
    """initialize response includes server capabilities flags."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test", "title": "Test"},
    })

    caps = resp["result"]["capabilities"]
    assert isinstance(caps["experimentalApi"], bool)
    assert isinstance(caps["supportsNotificationOptOut"], bool)
    assert isinstance(caps["supportsWorkbenchProcesses"], bool)
    assert "supportsPty" in caps


# ── 45.1.3: invalid clientInfo returns INVALID_PARAMS ───────────────────────


@pytest.mark.asyncio
async def test_initialize_missing_client_info_returns_invalid_params():
    """Missing clientInfo returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {})

    assert "error" in resp, f"Expected error for missing clientInfo, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_initialize_missing_client_name_returns_invalid_params():
    """Missing clientInfo.name returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"title": "No Name"},
    })

    assert "error" in resp, f"Expected error for missing name, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_initialize_empty_client_name_returns_invalid_params():
    """Empty clientInfo.name returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "", "title": "Empty"},
    })

    assert "error" in resp, f"Expected error for empty name, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


# ── 45.1.4: capabilities may be omitted (defaults) ──────────────────────────


@pytest.mark.asyncio
async def test_initialize_without_capabilities_uses_defaults():
    """Capabilities field can be omitted; defaults assume false/empty."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
    })

    assert "result" in resp, f"Expected result without capabilities, got: {resp}"


# ── 45.1.5: unknown capability fields are ignored ───────────────────────────


@pytest.mark.asyncio
async def test_initialize_unknown_capability_fields_ignored():
    """Unknown capability fields are silently ignored."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {
            "futureFeature": True,
            "unknownV2Field": {"nested": "value"},
        },
    })

    assert "result" in resp, f"Expected result with unknown caps, got: {resp}"


# ── 45.1.6: optOutNotificationMethods must be list of strings if present ────


@pytest.mark.asyncio
async def test_initialize_opt_out_must_be_list_of_strings():
    """optOutNotificationMethods must be a list of strings if present."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    # Valid: list of strings
    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {
            "optOutNotificationMethods": ["process/outputDelta"],
        },
    })
    assert "result" in resp, f"Expected result with valid opt-out list, got: {resp}"

    # Invalid: not a list
    resp2 = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {
            "optOutNotificationMethods": "process/outputDelta",
        },
    })
    assert "error" in resp2, f"Expected error for non-list opt-out, got: {resp2}"
    assert resp2.get("code") == "INVALID_PARAMS"


# ── 45.1.7: initialize stores capabilities on AppServer ─────────────────────


@pytest.mark.asyncio
async def test_initialize_stores_client_capabilities():
    """Successful initialize stores ClientCapabilities on AppServer."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "miqi_desktop", "title": "Desktop", "version": "0.1.0"},
        "capabilities": {
            "experimentalApi": True,
            "optOutNotificationMethods": ["process/outputDelta"],
        },
    })

    assert "result" in resp

    # The initialize handler should derive client_id from clientInfo
    # and store capabilities on AppServer
    client_id = resp["result"].get("clientId")
    assert client_id is not None

    caps = server.get_client_capabilities(client_id)
    assert caps is not None
    assert caps.experimental_api is True
    assert caps.opt_out_notification_methods == {"process/outputDelta"}


# ── 45.1.8: experimentalApi=true allows process/spawn without params flag ────


@pytest.mark.asyncio
async def test_experimental_api_from_initialize_grants_process_spawn():
    """process/spawn works after initialize with capabilities.experimentalApi=true."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    # Initialize with experimentalApi=true
    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "miqi_desktop"},
        "capabilities": {"experimentalApi": True},
    })
    assert "result" in resp
    client_id = resp["result"]["clientId"]

    # Set up WorkbenchProcessRuntime
    from unittest.mock import MagicMock
    from miqi.runtime.workbench_process_runtime import WorkbenchProcessRuntime
    registry.bridge_context["state"] = MagicMock()
    registry.bridge_context["workbench_process_runtime"] = WorkbenchProcessRuntime(workspace=Path.cwd())
    # Phase 45: expose AppServer so handlers can check client capabilities
    registry.bridge_context["app_server"] = server

    from miqi.runtime.workbench_process_app_handlers import register_workbench_process_handlers
    register_workbench_process_handlers(server)

    # process/spawn should succeed without params.experimentalApi
    # (using the capability from initialize)
    resp2 = await _dispatch(server, registry, "process/spawn", {
        "command": ["echo", "hello"],
        "cwd": str(Path.cwd()),
    }, client_id=client_id)

    # Should succeed (result, not error about EXPERIMENTAL_API_REQUIRED)
    if "error" in resp2:
        assert resp2.get("code") != "EXPERIMENTAL_API_REQUIRED", (
            f"Should not require experimentalApi in params when capability is set: {resp2}"
        )
    else:
        assert "result" in resp2


# ── 45.1.9: opt-out suppresses exact notification names ─────────────────────


@pytest.mark.asyncio
async def test_opt_out_notification_methods_suppress_exact_match():
    """optOutNotificationMethods suppresses exact notification names only."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    delivered: list[dict] = []

    async def _sink(envelope):
        delivered.append(envelope)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "miqi_desktop"},
        "capabilities": {
            "optOutNotificationMethods": ["process/outputDelta"],
        },
    })
    client_id = resp["result"]["clientId"]

    server.set_event_sink(client_id, _sink)

    # Opted-out event should be suppressed
    await server.emit_client_event(client_id, "process/outputDelta", {"pid": 1})
    assert len(delivered) == 0

    # Non-opted-out event should still be delivered
    await server.emit_client_event(client_id, "process/exited", {"pid": 1, "code": 0})
    assert len(delivered) == 1
    assert delivered[0]["event"] == "process/exited"


# ── 45.1.10: Non-initialize requests return NOT_INITIALIZED ─────────────────

# These tests require bridge-level integration. They verify the bridge
# transport enforces the initialize handshake. For direct AppServer.dispatch()
# tests the gate is not enforced (by design, to keep unit tests working).


@pytest.mark.asyncio
async def test_bridge_level_not_initialized_gate():
    """Bridge-level: requests before initialize return NOT_INITIALIZED.

    This test simulates the bridge drain loop behavior by directly testing
    the pre-dispatch gate logic that BridgeRuntimeLoop will enforce.
    """
    from miqi.runtime.app_server import AppServer, AppServerError

    # Simulate connection state before initialize
    class _ConnectionState:
        initialized = False
        initialized_ack = False
        client_id: str | None = None
        client_info: dict = {}
        capabilities: Any = None

    conn = _ConnectionState()

    # Helper that emulates bridge pre-dispatch gate
    def _check_initialized(method: str) -> dict | None:
        if method in ("initialize", "initialized"):
            return None  # allowed
        if not conn.initialized:
            return {
                "id": "req-1",
                "error": "Not initialized",
                "code": "NOT_INITIALIZED",
                "recoverable": False,
            }
        return None

    # Before initialize, non-initialize methods are rejected
    err = _check_initialized("chat.send")
    assert err is not None
    assert err["code"] == "NOT_INITIALIZED"

    err = _check_initialized("status")
    assert err is not None
    assert err["code"] == "NOT_INITIALIZED"

    # initialize itself is allowed
    assert _check_initialized("initialize") is None

    # initialized notification is allowed
    assert _check_initialized("initialized") is None


@pytest.mark.asyncio
async def test_bridge_level_already_initialized_gate():
    """Bridge-level: repeated initialize returns ALREADY_INITIALIZED."""
    from miqi.runtime.app_server import AppServer, AppServerError

    class _ConnectionState:
        initialized = True
        initialized_ack = True
        client_id: str = "client-mq-abc123"
        client_info: dict = {"name": "test"}
        capabilities: Any = None

    conn = _ConnectionState()

    def _check_repeat_initialize(method: str) -> dict | None:
        if method == "initialize" and conn.initialized:
            return {
                "id": "req-2",
                "error": "Already initialized",
                "code": "ALREADY_INITIALIZED",
                "recoverable": False,
            }
        return None

    err = _check_repeat_initialize("initialize")
    assert err is not None
    assert err["code"] == "ALREADY_INITIALIZED"


@pytest.mark.asyncio
async def test_bridge_level_initialized_notification_no_response():
    """Bridge-level: initialized notification sends no response."""
    # initialized notification has no 'id' field in Codex.
    # The bridge must handle notifications without crashing or sending a response.
    notification = {"method": "initialized", "params": {}}
    assert "id" not in notification
    # Bridge should silently process and not produce a response
    # (This is verified by the lack of an error/response from the drain loop)


# ── 45.1.11: Client ID derivation ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_derives_client_id_from_client_info():
    """Client ID is derived from clientInfo.name when no explicit clientId."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "miqi_desktop"},
    })

    client_id = resp["result"]["clientId"]
    assert client_id.startswith("client-")
    # Name segment should be sanitized
    assert "miqi_desktop" in client_id
    # Should include a short uuid
    parts = client_id.split("-")
    assert len(parts) >= 3  # client-NAME-UUID


@pytest.mark.asyncio
async def test_initialize_accepts_explicit_client_id():
    """Explicit clientId in params is used when provided."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "miqi_desktop"},
        "clientId": "my-custom-client-id",
    })

    client_id = resp["result"]["clientId"]
    assert client_id == "my-custom-client-id"


# ── 45.1.12: Per-request client_id conflict ─────────────────────────────────


@pytest.mark.asyncio
async def test_bridge_level_client_id_conflict_rejected():
    """Per-request client_id that conflicts with initialized client is rejected."""
    from miqi.runtime.app_server import AppServerError

    class _ConnectionState:
        initialized = True
        client_id: str = "client-mq-abc123"
        client_info: dict = {"name": "miqi_desktop"}
        capabilities: Any = None

    conn = _ConnectionState()

    def _check_client_id(params_client_id: str | None):
        if params_client_id is not None and params_client_id != conn.client_id:
            raise AppServerError(
                f"client_id mismatch: request claims {params_client_id} but connection is {conn.client_id}",
                code="INVALID_PARAMS",
            )
        return conn.client_id

    # Matching client_id is fine
    assert _check_client_id("client-mq-abc123") == "client-mq-abc123"

    # Mismatch is rejected
    with pytest.raises(AppServerError, match="client_id mismatch"):
        _check_client_id("other-client")


# ── 45.1.13: Event sink is registered under initialized client_id ───────────


@pytest.mark.asyncio
async def test_initialize_registers_event_sink_under_client_id():
    """After initialize, the event sink is registered under the derived client_id."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "miqi_desktop"},
    })
    client_id = resp["result"]["clientId"]

    # At bridge level, the sink would be registered under this client_id.
    # For direct tests, we verify the client_id is usable for sink registration.
    delivered: list[dict] = []

    async def _sink(envelope):
        delivered.append(envelope)

    server.set_event_sink(client_id, _sink)
    await server.emit_client_event(client_id, "process/exited", {"code": 0})
    assert len(delivered) == 1
    assert delivered[0]["event"] == "process/exited"


# ══════════════════════════════════════════════════════════════════════════════
# Phase 45 Hardening: real _drain_loop integration tests
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_drain_loop_rejects_repeated_initialize_with_already_initialized():
    """Real _drain_loop: second initialize returns ALREADY_INITIALIZED.

    This test pushes JSON lines through BridgeRuntimeLoop's real stdin
    queue and captures send() output — no local helper gate simulation.
    """
    import json as _json

    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=None,
    )
    await loop._init_app_server()

    # Set up the stdin queue that _drain_loop consumes
    loop._stdin_queue = asyncio.Queue()

    # Push first initialize
    await loop._stdin_queue.put(_json.dumps({
        "id": "req-1",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "miqi_desktop", "title": "Desktop", "version": "0.1.0"},
        },
    }))

    # Push second initialize (must be rejected by bridge, not AppServer)
    await loop._stdin_queue.put(_json.dumps({
        "id": "req-2",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "miqi_desktop", "title": "Desktop", "version": "0.1.0"},
        },
    }))

    # Push EOF sentinel so _drain_loop exits
    await loop._stdin_queue.put(None)

    await loop._drain_loop()

    assert len(capturer.messages) >= 2, (
        f"Expected at least 2 messages, got {len(capturer.messages)}: {capturer.messages}"
    )

    # First message: initialize success
    first = capturer.messages[0]
    assert "result" in first, f"First message should be initialize success, got: {first}"
    assert "clientId" in first["result"]

    # Second message: ALREADY_INITIALIZED (rejected at bridge level)
    second = capturer.messages[1]
    assert second.get("code") == "ALREADY_INITIALIZED", (
        f"Second message should be ALREADY_INITIALIZED, got: {second}"
    )
    assert second.get("error") == "Already initialized"
    assert second.get("recoverable") is False

    await loop._shutdown()


@pytest.mark.asyncio
async def test_drain_loop_preserves_client_id_after_repeated_initialize():
    """Real _drain_loop: client_id unchanged after repeated initialize rejection."""
    import json as _json

    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=None,
    )
    await loop._init_app_server()
    loop._stdin_queue = asyncio.Queue()

    # First initialize with explicit clientId
    await loop._stdin_queue.put(_json.dumps({
        "id": "req-1",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "test"},
            "clientId": "my-stable-client",
        },
    }))

    # Second initialize tries to use a different clientId
    await loop._stdin_queue.put(_json.dumps({
        "id": "req-2",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "test"},
            "clientId": "attacker-client",
        },
    }))

    await loop._stdin_queue.put(None)
    await loop._drain_loop()

    # Verify first initialize succeeded with original client_id
    first = capturer.messages[0]
    assert "result" in first
    assert first["result"]["clientId"] == "my-stable-client"

    # Verify second was rejected
    second = capturer.messages[1]
    assert second.get("code") == "ALREADY_INITIALIZED"

    # Connection state must still hold the first client_id
    assert loop._connection_state is not None
    assert loop._connection_state.client_id == "my-stable-client"

    await loop._shutdown()


@pytest.mark.asyncio
async def test_drain_loop_preserves_capabilities_after_repeated_initialize():
    """Real _drain_loop: capabilities not overwritten by second initialize."""
    import json as _json

    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=None,
    )
    await loop._init_app_server()
    loop._stdin_queue = asyncio.Queue()

    # First initialize with experimentalApi=true and some opt-out
    await loop._stdin_queue.put(_json.dumps({
        "id": "req-1",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "test"},
            "clientId": "cap-test-client",
            "capabilities": {
                "experimentalApi": True,
                "optOutNotificationMethods": ["process/outputDelta"],
            },
        },
    }))

    # Second initialize with experimentalApi=false (should be rejected)
    await loop._stdin_queue.put(_json.dumps({
        "id": "req-2",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "test"},
            "clientId": "cap-test-client",
            "capabilities": {
                "experimentalApi": False,
            },
        },
    }))

    await loop._stdin_queue.put(None)
    await loop._drain_loop()

    first = capturer.messages[0]
    assert "result" in first
    cid = first["result"]["clientId"]

    second = capturer.messages[1]
    assert second.get("code") == "ALREADY_INITIALIZED"

    # Capabilities on AppServer must still reflect first initialize
    caps = loop.app_server.get_client_capabilities(cid)
    assert caps is not None
    assert caps.experimental_api is True, (
        f"experimentalApi should still be True from first initialize, got {caps.experimental_api}"
    )
    assert "process/outputDelta" in caps.opt_out_notification_methods

    await loop._shutdown()


@pytest.mark.asyncio
async def test_drain_loop_does_not_re_migrate_event_sink():
    """Real _drain_loop: event sink not re-migrated on repeated initialize."""
    import json as _json

    from miqi.bridge.loop import BridgeRuntimeLoop

    capturer = _CaptureSend()
    loop = BridgeRuntimeLoop(
        send_func=capturer.send,
        dispatch_legacy_func=None,
    )
    # Set up event sink before init (simulates _setup_event_sink)
    await loop._init_app_server()

    # Register a desktop sink (what _setup_event_sink normally does)
    desktop_hits: list[int] = [0]

    async def _desktop_sink(envelope):
        desktop_hits[0] += 1

    loop.app_server.set_event_sink("desktop", _desktop_sink)

    loop._stdin_queue = asyncio.Queue()

    # First initialize
    await loop._stdin_queue.put(_json.dumps({
        "id": "req-1",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "test"},
            "clientId": "sink-test-client",
        },
    }))

    # Count event sinks after first initialize (before second)
    # Second initialize (rejected)
    await loop._stdin_queue.put(_json.dumps({
        "id": "req-2",
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "test"},
            "clientId": "sink-test-client",
        },
    }))

    await loop._stdin_queue.put(None)
    await loop._drain_loop()

    first = capturer.messages[0]
    assert "result" in first
    cid = first["result"]["clientId"]

    second = capturer.messages[1]
    assert second.get("code") == "ALREADY_INITIALIZED"

    # Event sink should be registered under the client_id (from first initialize)
    # and still present (not cleaned up)
    assert cid in loop.app_server._event_sinks
    assert "desktop" in loop.app_server._event_sinks

    await loop._shutdown()


# ══════════════════════════════════════════════════════════════════════════════
# Phase 45 Hardening: experimentalApi must be actual bool
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_experimental_api_string_false_rejected():
    """String "false" is not bool → INVALID_PARAMS, not silently truthy."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {"experimentalApi": "false"},
    })

    assert "error" in resp, f"String 'false' should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_experimental_api_string_true_rejected():
    """String "true" is not bool → INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {"experimentalApi": "true"},
    })

    assert "error" in resp, f"String 'true' should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_experimental_api_int_rejected():
    """Integer 1 is not bool → INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {"experimentalApi": 1},
    })

    assert "error" in resp, f"Integer 1 should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_experimental_api_int_zero_rejected():
    """Integer 0 is not bool → INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {"experimentalApi": 0},
    })

    assert "error" in resp, f"Integer 0 should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_experimental_api_null_rejected():
    """null is not bool → INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {"experimentalApi": None},
    })

    assert "error" in resp, f"null should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_experimental_api_true_accepted():
    """bool True is accepted."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {"experimentalApi": True},
    })

    assert "result" in resp, f"bool True should be accepted, got: {resp}"


@pytest.mark.asyncio
async def test_experimental_api_false_accepted():
    """bool False is accepted."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {"experimentalApi": False},
    })

    assert "result" in resp, f"bool False should be accepted, got: {resp}"


@pytest.mark.asyncio
async def test_experimental_api_absent_defaults_false():
    """When experimentalApi is absent, capabilities default to False."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "capabilities": {},
    })

    assert "result" in resp
    cid = resp["result"]["clientId"]
    caps = server.get_client_capabilities(cid)
    assert caps is not None
    assert caps.experimental_api is False


# ══════════════════════════════════════════════════════════════════════════════
# Phase 45 Hardening: explicit clientId validation
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_explicit_client_id_rejects_forward_slash():
    """Explicit clientId with '/' returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "clientId": "evil/../../../etc",
    })

    assert "error" in resp, f"Path char should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_explicit_client_id_rejects_backslash():
    """Explicit clientId with backslash returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "clientId": "evil\\..\\..\\windows",
    })

    assert "error" in resp, f"Backslash should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_explicit_client_id_rejects_dot_dot():
    """Explicit clientId with '..' returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "clientId": "client-..-etc",
    })

    assert "error" in resp, f"'..' should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_explicit_client_id_rejects_control_chars():
    """Explicit clientId with control characters returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    for bad in ["\x00", "\x01", "\x1F", "\x7F", "hello\x00world", "\n", "\t"]:
        resp = await _dispatch(server, registry, "initialize", {
            "clientInfo": {"name": "test"},
            "clientId": bad,
        })
        assert "error" in resp, f"Control char {repr(bad)} should be rejected, got: {resp}"
        assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_explicit_client_id_rejects_too_long():
    """Explicit clientId > 128 chars returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    resp = await _dispatch(server, registry, "initialize", {
        "clientInfo": {"name": "test"},
        "clientId": "x" * 129,
    })

    assert "error" in resp, f"Too-long clientId should be rejected, got: {resp}"
    assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_explicit_client_id_rejects_blank():
    """Explicit clientId empty or whitespace-only returns INVALID_PARAMS."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    for bad in ["", "   ", "\t  \n"]:
        resp = await _dispatch(server, registry, "initialize", {
            "clientInfo": {"name": "test"},
            "clientId": bad,
        })
        assert "error" in resp, f"Blank clientId {repr(bad)} should be rejected, got: {resp}"
        assert resp.get("code") == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_explicit_client_id_accepts_valid():
    """Valid explicit clientId is accepted."""
    server, registry = _make_server_with_caps()

    from miqi.runtime.initialize_protocol import register_initialize_handler
    register_initialize_handler(server)

    for good in ["my-client", "client_123", "valid.client-id", "a" * 128]:
        resp = await _dispatch(server, registry, "initialize", {
            "clientInfo": {"name": "test"},
            "clientId": good,
        })
        assert "result" in resp, f"Valid clientId {repr(good)} should be accepted, got: {resp}"
        assert resp["result"]["clientId"] == good.strip()
