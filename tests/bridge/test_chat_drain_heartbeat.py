"""Tests for the chat drain heartbeat (#798).

The frontend watchdog treats 60s without progress events as a dead
backend, but turns legitimately stay silent for minutes (model thinking,
long exec without stdout) while the drain's own idle timeout is 600s.
The drain must emit a heartbeat progress event every
CHAT_HEARTBEAT_INTERVAL_SECONDS so the frontend sees liveness, and stop
heartbeating once the turn finishes.
"""

import asyncio

import pytest

from miqi.bridge import loop as loop_mod
from miqi.bridge.loop import BridgeRuntimeLoop
from miqi.protocol.events import TurnCompleteEvent, TurnStartedEvent


class _FakeAppServer:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str]] = []

    async def emit_event(self, session_id, event_type, data, request_id=None):
        self.emitted.append(
            (event_type, dict(data) if isinstance(data, dict) else data, session_id)
        )


class _FakeRuntime:
    """Yields the given events; sleeps *first_delay* before the first one."""

    def __init__(self, events, first_delay: float = 0.0):
        self._events = list(events)
        self._delay = first_delay

    async def next_event(self, timeout=None):
        if self._delay > 0:
            await asyncio.sleep(self._delay)
            self._delay = 0.0
        return self._events.pop(0) if self._events else None


def _drain_kwargs():
    return dict(
        request_id="req1",
        runtime=None,  # set per test
        thread_id="sess",
        session_id="c:sess",
        client_id="c",
        session_key="sess",
    )


@pytest.mark.asyncio
async def test_drain_emits_heartbeat_while_turn_is_silent(monkeypatch):
    monkeypatch.setattr(loop_mod, "CHAT_HEARTBEAT_INTERVAL_SECONDS", 0.05)

    loop = BridgeRuntimeLoop(send_func=lambda msg: None)
    app = _FakeAppServer()
    loop._app_server = app

    runtime = _FakeRuntime(
        [
            TurnStartedEvent(turn_id="t1", agent_name="a", thread_id="sess"),
            TurnCompleteEvent(turn_id="t1", thread_id="sess", outcome="success"),
        ],
        first_delay=0.15,
    )
    kwargs = _drain_kwargs()
    kwargs["runtime"] = runtime
    await loop._drain_chat_events(**kwargs)

    heartbeats = [
        data
        for (etype, data, _sess) in app.emitted
        if etype == "progress" and data.get("stream") == "heartbeat"
    ]
    assert heartbeats, "drain must emit heartbeat progress events while the turn is silent"
    assert all(d.get("session_key") == "sess" for d in heartbeats)


@pytest.mark.asyncio
async def test_drain_heartbeat_stops_after_turn_completes(monkeypatch):
    monkeypatch.setattr(loop_mod, "CHAT_HEARTBEAT_INTERVAL_SECONDS", 0.05)

    loop = BridgeRuntimeLoop(send_func=lambda msg: None)
    app = _FakeAppServer()
    loop._app_server = app

    runtime = _FakeRuntime(
        [TurnCompleteEvent(turn_id="t1", thread_id="sess", outcome="success")],
        first_delay=0.1,
    )
    kwargs = _drain_kwargs()
    kwargs["runtime"] = runtime
    await loop._drain_chat_events(**kwargs)

    emitted_after_drain = len(app.emitted)
    await asyncio.sleep(0.2)
    assert len(app.emitted) == emitted_after_drain, (
        "heartbeat must stop once the drain finishes"
    )
