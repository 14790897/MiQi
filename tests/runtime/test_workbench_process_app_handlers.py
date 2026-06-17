"""Tests for workbench process/* AppServer handlers (Phase 43.5)."""

import asyncio
from pathlib import Path

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_server():
    """Create an AppServer with WorkbenchProcessRuntime in bridge_context."""
    from unittest.mock import MagicMock

    from miqi.runtime.app_server import AppServer, ClientSessionRegistry
    from miqi.runtime.workbench_process_runtime import WorkbenchProcessRuntime

    registry = ClientSessionRegistry()
    registry.bridge_context = {
        "state": MagicMock(),
        "workbench_process_runtime": WorkbenchProcessRuntime(workspace=Path.cwd()),
    }
    server = AppServer(registry)
    return server, registry


async def _dispatch(server, registry, method, params, client_id="test-client", session_id=None):
    """Dispatch a request and return the response dict."""
    resp = await server.dispatch(
        request_id="req-1",
        method=method,
        params=params,
        client_id=client_id,
        session_id=session_id,
    )
    return resp


@pytest.fixture
def server_and_registry():
    """Fixture providing AppServer with process handlers registered."""
    from miqi.runtime.workbench_process_app_handlers import (
        register_workbench_process_handlers,
    )

    server, registry = _make_server()
    register_workbench_process_handlers(server)
    return server, registry


# ── process/spawn ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_spawn_returns_empty_result_immediately(server_and_registry):
    """process/spawn returns {} immediately — does not wait for exit."""
    import time

    server, registry = server_and_registry

    t0 = time.monotonic()
    resp = await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "import time; time.sleep(30)"],
        "processHandle": "spawn-slow",
        "cwd": str(Path.cwd()),
    })
    elapsed = time.monotonic() - t0

    assert "result" in resp, f"Expected result, got: {resp}"
    assert elapsed < 2.0, f"spawn should return immediately, took {elapsed:.1f}s"

    # Cleanup: kill the spawned process
    wpr = registry.bridge_context["workbench_process_runtime"]
    try:
        await wpr.kill("test-client", "spawn-slow")
    except Exception:
        pass


@pytest.mark.asyncio
async def test_process_spawn_emits_output_delta(server_and_registry):
    """process/spawn emits process/outputDelta events."""
    import asyncio as _asyncio

    server, registry = server_and_registry
    events_received: list = []

    async def fake_sink(envelope):
        events_received.append(envelope)

    server.set_event_sink("test-client", fake_sink)

    resp = await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "print('hello-spawn')"],
        "processHandle": "spawn-stream",
        "cwd": str(Path.cwd()),
    })
    assert "result" in resp, f"Expected result, got: {resp}"

    # Wait for output
    await _asyncio.sleep(0.5)

    output_deltas = [
        e for e in events_received
        if e.get("event") == "process/outputDelta"
    ]
    assert len(output_deltas) > 0, (
        f"Expected process/outputDelta events, got: {events_received}"
    )

    # Wait for exit notification
    await _asyncio.sleep(0.5)
    exit_events = [
        e for e in events_received
        if e.get("event") == "process/exited"
    ]
    assert len(exit_events) > 0, (
        f"Expected process/exited event, got: {events_received}"
    )


@pytest.mark.asyncio
async def test_process_spawn_emits_exited_notification(server_and_registry):
    """process/spawn emits process/exited notification when process finishes."""
    import asyncio as _asyncio

    server, registry = server_and_registry
    events_received: list = []

    async def fake_sink(envelope):
        events_received.append(envelope)

    server.set_event_sink("test-client", fake_sink)

    await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "print('done')"],
        "processHandle": "spawn-exit",
        "cwd": str(Path.cwd()),
    })

    # Wait for exit
    for _ in range(20):
        await _asyncio.sleep(0.1)
        exit_events = [
            e for e in events_received
            if e.get("event") == "process/exited"
        ]
        if exit_events:
            break

    exit_events = [
        e for e in events_received
        if e.get("event") == "process/exited"
    ]
    assert len(exit_events) > 0, (
        f"Expected process/exited event, got: {events_received}"
    )
    exit_data = exit_events[0]["data"]
    assert exit_data["exitCode"] == 0
    assert "done" in exit_data.get("stdout", "")


@pytest.mark.asyncio
async def test_process_spawn_missing_experimental_flag_rejected(server_and_registry):
    """process/spawn without experimentalApi flag returns EXPERIMENTAL_API_REQUIRED."""
    server, registry = server_and_registry

    resp = await _dispatch(server, registry, "process/spawn", {
        "command": ["python", "-c", "print('hi')"],
        "processHandle": "no-exp-flag",
        "cwd": str(Path.cwd()),
    })
    assert "error" in resp, f"Expected error without experimentalApi, got: {resp}"
    assert resp.get("code") == "EXPERIMENTAL_API_REQUIRED", (
        f"Expected EXPERIMENTAL_API_REQUIRED, got: {resp.get('code')}"
    )


@pytest.mark.asyncio
async def test_process_spawn_tty_true_rejected(server_and_registry):
    """process/spawn with tty:true returns UNSUPPORTED_FEATURE."""
    server, registry = server_and_registry

    resp = await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "print('hi')"],
        "processHandle": "tty-spawn",
        "cwd": str(Path.cwd()),
        "tty": True,
    })
    assert "error" in resp, f"Expected error for tty:true, got: {resp}"
    assert resp.get("code") == "UNSUPPORTED_FEATURE", (
        f"Expected UNSUPPORTED_FEATURE, got: {resp.get('code')}"
    )


@pytest.mark.asyncio
async def test_process_spawn_duplicate_handle_rejected(server_and_registry):
    """Duplicate processHandle is rejected."""
    import asyncio as _asyncio

    server, registry = server_and_registry

    # Spawn a long-running process
    resp1 = await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "import time; time.sleep(10)"],
        "processHandle": "dup-spawn",
        "cwd": str(Path.cwd()),
    })
    assert "result" in resp1

    await _asyncio.sleep(0.1)

    resp2 = await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "print('hi')"],
        "processHandle": "dup-spawn",
        "cwd": str(Path.cwd()),
    })
    assert "error" in resp2, f"Expected error for duplicate handle, got: {resp2}"

    # Cleanup
    wpr = registry.bridge_context["workbench_process_runtime"]
    try:
        await wpr.kill("test-client", "dup-spawn")
    except Exception:
        pass


# ── process/writeStdin ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_write_stdin_works(server_and_registry):
    """process/writeStdin writes to process stdin."""
    import asyncio as _asyncio
    import base64

    server, registry = server_and_registry
    events_received: list = []

    async def fake_sink(envelope):
        events_received.append(envelope)

    server.set_event_sink("test-client", fake_sink)

    await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c",
                    "import sys; data=sys.stdin.read(); print('READ:'+data)"],
        "processHandle": "spawn-stdin",
        "cwd": str(Path.cwd()),
    })
    await _asyncio.sleep(0.1)

    resp = await _dispatch(server, registry, "process/writeStdin", {
        "processHandle": "spawn-stdin",
        "deltaBase64": base64.b64encode(b"hello-spawn-stdin").decode(),
    })
    assert "result" in resp, f"Expected result from writeStdin, got: {resp}"

    # Close stdin
    await _dispatch(server, registry, "process/writeStdin", {
        "processHandle": "spawn-stdin",
        "closeStdin": True,
    })

    # Wait for exit
    for _ in range(20):
        await _asyncio.sleep(0.1)
        exit_events = [
            e for e in events_received
            if e.get("event") == "process/exited"
        ]
        if exit_events:
            break

    exit_events = [
        e for e in events_received
        if e.get("event") == "process/exited"
    ]
    assert len(exit_events) > 0
    assert "READ:hello-spawn-stdin" in exit_events[0]["data"].get("stdout", "")


# ── process/kill ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_kill_terminates_running_process(server_and_registry):
    """process/kill terminates a running process."""
    import asyncio as _asyncio

    server, registry = server_and_registry
    events_received: list = []

    async def fake_sink(envelope):
        events_received.append(envelope)

    server.set_event_sink("test-client", fake_sink)

    await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "import time; time.sleep(30)"],
        "processHandle": "spawn-kill",
        "cwd": str(Path.cwd()),
    })
    await _asyncio.sleep(0.2)

    resp = await _dispatch(server, registry, "process/kill", {
        "processHandle": "spawn-kill",
    })
    assert "result" in resp, f"Expected result from kill, got: {resp}"

    # Should get exited event with non-zero exit code
    await _asyncio.sleep(0.5)
    exit_events = [
        e for e in events_received
        if e.get("event") == "process/exited"
    ]
    assert len(exit_events) > 0, (
        f"Expected process/exited after kill, got: {events_received}"
    )


# ── process/resizePty ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_resize_pty_returns_unsupported_feature(server_and_registry):
    """process/resizePty returns UNSUPPORTED_FEATURE in Phase 43."""
    server, registry = server_and_registry

    resp = await _dispatch(server, registry, "process/resizePty", {
        "processHandle": "any-handle",
        "size": {"rows": 24, "cols": 80},
    })
    assert "error" in resp
    assert resp.get("code") == "UNSUPPORTED_FEATURE", (
        f"Expected UNSUPPORTED_FEATURE, got: {resp.get('code')}"
    )


# ── Cross-client isolation ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_client_kill_rejected(server_and_registry):
    """Client A cannot kill client B's process."""
    import asyncio as _asyncio

    server, registry = server_and_registry

    # Client A spawns
    await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "import time; time.sleep(10)"],
        "processHandle": "cross-kill",
        "cwd": str(Path.cwd()),
    }, client_id="client-a")
    await _asyncio.sleep(0.1)

    # Client B tries to kill
    resp = await _dispatch(server, registry, "process/kill", {
        "processHandle": "cross-kill",
    }, client_id="client-b")
    assert "error" in resp, f"Expected error for cross-client kill, got: {resp}"

    # Cleanup
    wpr = registry.bridge_context["workbench_process_runtime"]
    try:
        await wpr.kill("client-a", "cross-kill")
    except Exception:
        pass


@pytest.mark.asyncio
async def test_cross_client_write_rejected(server_and_registry):
    """Client A cannot write to client B's process."""
    import asyncio as _asyncio
    import base64

    server, registry = server_and_registry

    await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c",
                    "import sys; sys.stdin.read(); print('DONE')"],
        "processHandle": "cross-write",
        "cwd": str(Path.cwd()),
    }, client_id="client-a")
    await _asyncio.sleep(0.1)

    resp = await _dispatch(server, registry, "process/writeStdin", {
        "processHandle": "cross-write",
        "deltaBase64": base64.b64encode(b"x").decode(),
    }, client_id="client-b")
    assert "error" in resp, f"Expected error for cross-client write, got: {resp}"

    # Cleanup
    wpr = registry.bridge_context["workbench_process_runtime"]
    try:
        await wpr.kill("client-a", "cross-write")
    except Exception:
        pass


# ── Client disconnect cleanup ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_client_disconnect_kills_live_process(server_and_registry):
    """When client event sink is removed, live processes are killed."""
    import asyncio as _asyncio

    server, registry = server_and_registry

    # Register client cleanup hook (normally done by BridgeRuntimeLoop)
    wpr = registry.bridge_context["workbench_process_runtime"]

    async def _kill_client_hook(client_id: str) -> None:
        await wpr.kill_client(client_id)

    server.add_client_cleanup_hook(_kill_client_hook)

    # Spawn a long-running process
    await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "import time; time.sleep(30)"],
        "processHandle": "disconnect-test",
        "cwd": str(Path.cwd()),
    }, client_id="client-disc")
    await _asyncio.sleep(0.2)

    # Verify process is alive
    wpr = registry.bridge_context["workbench_process_runtime"]
    assert wpr.get_handle("client-disc", "disconnect-test") is not None

    # Simulate disconnect by removing event sink (triggers cleanup hook)
    await server.remove_event_sink("client-disc")

    await _asyncio.sleep(0.3)

    # Process should be gone
    assert wpr.get_handle("client-disc", "disconnect-test") is None


@pytest.mark.asyncio
async def test_process_handle_reused_after_exit(server_and_registry):
    """After process exits, handle can be reused."""
    server, registry = server_and_registry

    await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "print('first')"],
        "processHandle": "reuse-spawn",
        "cwd": str(Path.cwd()),
    })
    import asyncio as _asyncio
    await _asyncio.sleep(0.3)

    resp = await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "print('second')"],
        "processHandle": "reuse-spawn",
        "cwd": str(Path.cwd()),
    })
    assert "result" in resp, f"Should be able to reuse handle after exit, got: {resp}"


# ── Validation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_handle_rejects_slashes(server_and_registry):
    """processHandle with slashes is rejected."""
    server, registry = server_and_registry

    resp = await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "print('hi')"],
        "processHandle": "bad/handle",
        "cwd": str(Path.cwd()),
    })
    assert "error" in resp


@pytest.mark.asyncio
async def test_process_handle_rejects_double_dot(server_and_registry):
    """processHandle with '..' is rejected."""
    server, registry = server_and_registry

    resp = await _dispatch(server, registry, "process/spawn", {
        "experimentalApi": True,
        "command": ["python", "-c", "print('hi')"],
        "processHandle": "../escape",
        "cwd": str(Path.cwd()),
    })
    assert "error" in resp
