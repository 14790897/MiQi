"""Phase 2 tests — EventBus, RuntimeEventRecorder, SSE encoder."""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from miqi.kun_runtime.event_bus import EventBus
from miqi.kun_runtime.event_recorder import RuntimeEventRecorder
from miqi.kun_runtime.sse import encode_sse, encode_sse_comment, encode_stream_final


# ═══════════════════════════════════════════════════════════════════════════════
# EventBus tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventBusSeq:
    def test_seq_starts_at_one(self) -> None:
        bus = EventBus()
        assert bus.allocate_seq("th1") == 1

    def test_seq_monotonic_per_thread(self) -> None:
        bus = EventBus()
        assert bus.allocate_seq("th1") == 1
        assert bus.allocate_seq("th1") == 2
        assert bus.allocate_seq("th1") == 3

    def test_seq_independent_across_threads(self) -> None:
        bus = EventBus()
        assert bus.allocate_seq("th1") == 1
        assert bus.allocate_seq("th1") == 2
        assert bus.allocate_seq("th2") == 1  # independent counter
        assert bus.allocate_seq("th2") == 2


class TestEventBusAppend:
    def test_append_stores_event(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "timestamp": "2026-01-01T00:00:00Z", "kind": "turn_started", "threadId": "th1"})
        assert bus.count("th1") == 1

    def test_append_preserves_order(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "kind": "turn_started"})
        bus.append("th1", {"seq": 2, "kind": "turn_completed"})
        bus.append("th1", {"seq": 3, "kind": "usage"})
        assert bus.count("th1") == 3


class TestEventBusHistory:
    def test_history_returns_all_when_since_seq_zero(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "kind": "turn_started"})
        bus.append("th1", {"seq": 2, "kind": "turn_completed"})
        result = bus.history("th1", since_seq=0)
        assert len(result) == 2

    def test_history_since_seq_filters(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "kind": "turn_started"})
        bus.append("th1", {"seq": 2, "kind": "turn_completed"})
        bus.append("th1", {"seq": 3, "kind": "usage"})
        result = bus.history("th1", since_seq=1)
        assert len(result) == 2
        kinds = [e["kind"] for e in result]
        assert "turn_started" not in kinds

    def test_history_unknown_thread_returns_empty(self) -> None:
        bus = EventBus()
        assert bus.history("no_such_thread") == []

    def test_history_empty_since_latest(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "kind": "turn_started"})
        result = bus.history("th1", since_seq=1)
        assert result == []


class TestEventBusCount:
    def test_count_zero_for_unknown(self) -> None:
        bus = EventBus()
        assert bus.count("unknown") == 0

    def test_count_tracks_appends(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "kind": "a"})
        bus.append("th1", {"seq": 2, "kind": "b"})
        assert bus.count("th1") == 2


# ═══════════════════════════════════════════════════════════════════════════════
# EventBus subscribe tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventBusSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_replays_history(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "kind": "turn_started", "threadId": "th1"})
        bus.append("th1", {"seq": 2, "kind": "turn_completed", "threadId": "th1"})

        collected: list[dict] = []
        async for event in bus.subscribe("th1", since_seq=0):
            collected.append(event)
            if len(collected) >= 2:
                break  # stop after history replay

        assert len(collected) == 2
        assert collected[0]["kind"] == "turn_started"

    @pytest.mark.asyncio
    async def test_subscribe_receives_new_events(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "kind": "turn_started", "threadId": "th1"})

        collected: list[dict] = []

        async def collect() -> None:
            async for event in bus.subscribe("th1", since_seq=1):
                collected.append(event)
                if len(collected) >= 1:
                    break

        task = asyncio.create_task(collect())
        # Give subscriber time to set up
        await asyncio.sleep(0.05)
        bus.append("th1", {"seq": 2, "kind": "usage", "threadId": "th1"})
        await asyncio.wait_for(task, timeout=2.0)

        assert len(collected) == 1
        assert collected[0]["kind"] == "usage"

    @pytest.mark.asyncio
    async def test_subscribe_since_seq_filters_history(self) -> None:
        bus = EventBus()
        bus.append("th1", {"seq": 1, "kind": "turn_started", "threadId": "th1"})
        bus.append("th1", {"seq": 2, "kind": "turn_completed", "threadId": "th1"})

        collected: list[dict] = []
        async for event in bus.subscribe("th1", since_seq=1):
            collected.append(event)
            if len(collected) >= 1:
                break

        assert len(collected) == 1
        assert collected[0]["seq"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# RuntimeEventRecorder tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuntimeEventRecorder:
    @pytest.mark.asyncio
    async def test_record_assigns_seq_and_timestamp(self) -> None:
        bus = EventBus()
        fixed_time = "2026-06-08T12:00:00Z"
        recorder = RuntimeEventRecorder(bus, now_iso=lambda: fixed_time)

        result = await recorder.record({"kind": "turn_started", "threadId": "th1"})

        assert result["seq"] == 1
        assert result["timestamp"] == fixed_time
        assert result["kind"] == "turn_started"
        assert bus.count("th1") == 1

    @pytest.mark.asyncio
    async def test_record_increments_seq(self) -> None:
        bus = EventBus()
        recorder = RuntimeEventRecorder(bus, now_iso=lambda: "2026-01-01T00:00:00Z")

        r1 = await recorder.record({"kind": "turn_started", "threadId": "th1"})
        r2 = await recorder.record({"kind": "turn_completed", "threadId": "th1"})
        r3 = await recorder.record({"kind": "usage", "threadId": "th1"})

        assert r1["seq"] == 1
        assert r2["seq"] == 2
        assert r3["seq"] == 3

    @pytest.mark.asyncio
    async def test_record_independent_threads(self) -> None:
        bus = EventBus()
        recorder = RuntimeEventRecorder(bus, now_iso=lambda: "2026-01-01T00:00:00Z")

        r1 = await recorder.record({"kind": "turn_started", "threadId": "th1"})
        r2 = await recorder.record({"kind": "turn_started", "threadId": "th2"})

        assert r1["seq"] == 1
        assert r2["seq"] == 1  # independent per thread

    @pytest.mark.asyncio
    async def test_record_rejects_empty_thread_id(self) -> None:
        bus = EventBus()
        recorder = RuntimeEventRecorder(bus)

        with pytest.raises(ValueError, match="threadId"):
            await recorder.record({"kind": "turn_started", "threadId": ""})

    @pytest.mark.asyncio
    async def test_record_events_appear_in_history(self) -> None:
        bus = EventBus()
        recorder = RuntimeEventRecorder(bus, now_iso=lambda: "2026-01-01T00:00:00Z")

        await recorder.record({"kind": "turn_started", "threadId": "th1", "turnId": "t1"})
        await recorder.record({"kind": "turn_completed", "threadId": "th1", "turnId": "t1"})

        events = bus.history("th1")
        assert len(events) == 2
        assert events[0]["turnId"] == "t1"


# ═══════════════════════════════════════════════════════════════════════════════
# SSE encoder tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSSEEncode:
    def test_basic_event(self) -> None:
        event = {"seq": 1, "kind": "turn_started", "threadId": "th1"}
        sse = encode_sse(event)
        # Should have id, event, data lines and a blank line
        assert "id: 1" in sse
        assert "event: turn_started" in sse
        assert "data:" in sse
        assert sse.endswith("\n\n")

    def test_event_lines_format(self) -> None:
        """Verify exact SSE field order: id, event, data"""
        event = {"seq": 5, "kind": "assistant_text_delta", "threadId": "th1", "turnId": "t1"}
        sse = encode_sse(event)
        lines = sse.strip().split("\n")
        assert lines[0].startswith("id: ")
        assert lines[1].startswith("event: ")
        assert lines[2].startswith("data: ")

    def test_json_in_data_is_valid(self) -> None:
        event = {"seq": 1, "kind": "usage", "threadId": "th1", "usage": {"promptTokens": 100}}
        sse = encode_sse(event)
        # Extract data line
        data_line = [l for l in sse.split("\n") if l.startswith("data: ")][0]
        payload = data_line[len("data: "):]
        parsed = json.loads(payload)
        assert parsed["kind"] == "usage"
        assert parsed["usage"]["promptTokens"] == 100

    def test_complex_nested_event(self) -> None:
        event = {
            "seq": 3,
            "kind": "tool_call_ready",
            "threadId": "th1",
            "turnId": "t1",
            "toolName": "read",
            "callId": "call_abc",
            "readyCount": 2,
        }
        sse = encode_sse(event)
        data_line = [l for l in sse.split("\n") if l.startswith("data: ")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed["toolName"] == "read"
        assert parsed["readyCount"] == 2

    def test_non_jsonable_values_use_str(self) -> None:
        """Values that aren't JSON-serializable should use str() fallback."""
        from datetime import datetime
        event = {"seq": 1, "kind": "heartbeat", "threadId": "th1", "ts": datetime(2026, 1, 1)}
        sse = encode_sse(event)
        data_line = [l for l in sse.split("\n") if l.startswith("data: ")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert "2026" in str(parsed["ts"])

    def test_special_characters(self) -> None:
        event = {"seq": 1, "kind": "error", "threadId": "th1", "message": "line1\nline2"}
        sse = encode_sse(event)
        data_line = [l for l in sse.split("\n") if l.startswith("data: ")][0]
        parsed = json.loads(data_line[len("data: "):])
        assert parsed["message"] == "line1\nline2"


class TestSSEComment:
    def test_comment_format(self) -> None:
        comment = encode_sse_comment("keepalive")
        assert comment == ": keepalive\n\n"


class TestSSEStreamFinal:
    def test_done_marker(self) -> None:
        done = encode_stream_final()
        assert done == "data: [DONE]\n\n"
