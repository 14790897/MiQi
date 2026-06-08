"""Phase 4 tests — ThreadService, TurnService, Cancellation, MigrationAdapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from miqi.kun_runtime.cancellation import CancellationToken, InflightTracker
from miqi.kun_runtime.event_bus import EventBus
from miqi.kun_runtime.event_recorder import RuntimeEventRecorder
from miqi.kun_runtime.migration_adapter import (
    clear_mapping,
    register_mapping,
    session_key_to_thread_id,
    thread_id_to_session_key,
)
from miqi.kun_runtime.stores import FileSessionStore, FileThreadStore
from miqi.kun_runtime.thread_service import ThreadService
from miqi.kun_runtime.turn_service import TurnService

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

FIXED_TIME = "2026-06-08T12:00:00Z"


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path / "kun_data"


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def events(bus: EventBus) -> RuntimeEventRecorder:
    return RuntimeEventRecorder(bus, now_iso=lambda: FIXED_TIME)


@pytest.fixture
def thread_store(tmp_dir: Path) -> FileThreadStore:
    return FileThreadStore(tmp_dir)


@pytest.fixture
def session_store(tmp_dir: Path) -> FileSessionStore:
    return FileSessionStore(tmp_dir)


@pytest.fixture
def inflight() -> InflightTracker:
    return InflightTracker()


@pytest.fixture
def thread_svc(thread_store: FileThreadStore, session_store: FileSessionStore, events: RuntimeEventRecorder) -> ThreadService:
    return ThreadService(thread_store, session_store, events, now_iso=lambda: FIXED_TIME)


@pytest.fixture
def turn_svc(
    thread_store: FileThreadStore,
    session_store: FileSessionStore,
    events: RuntimeEventRecorder,
    inflight: InflightTracker,
) -> TurnService:
    return TurnService(thread_store, session_store, events, inflight, now_iso=lambda: FIXED_TIME)


# ═══════════════════════════════════════════════════════════════════════════════
# CancellationToken tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCancellationToken:
    def test_initial_not_set(self) -> None:
        token = CancellationToken()
        assert not token.is_set()
        assert not token.cancelled

    def test_cancel_sets_flag(self) -> None:
        token = CancellationToken()
        token.cancel()
        assert token.is_set()
        assert token.cancelled

    @pytest.mark.asyncio
    async def test_wait_blocks_until_cancelled(self) -> None:
        import asyncio
        token = CancellationToken()
        async def canceller() -> None:
            await asyncio.sleep(0.05)
            token.cancel()
        asyncio.create_task(canceller())
        await asyncio.wait_for(token.wait(), timeout=1.0)
        assert token.is_set()

    def test_cancel_is_idempotent(self) -> None:
        token = CancellationToken()
        token.cancel()
        token.cancel()  # no error
        assert token.is_set()


class TestInflightTracker:
    def test_begin_and_count(self) -> None:
        tracker = InflightTracker()
        tracker.begin({"id": "op1", "kind": "model", "threadId": "th1"})
        assert tracker.count() == 1
        assert tracker.is_running("op1")

    def test_end_removes(self) -> None:
        tracker = InflightTracker()
        tracker.begin({"id": "op1", "kind": "model", "threadId": "th1"})
        tracker.end("op1")
        assert tracker.count() == 0
        assert not tracker.is_running("op1")

    def test_filter_by_thread(self) -> None:
        tracker = InflightTracker()
        tracker.begin({"id": "op1", "kind": "model", "threadId": "th1"})
        tracker.begin({"id": "op2", "kind": "tool", "threadId": "th2"})
        assert tracker.count("th1") == 1
        assert tracker.count("th2") == 1

    def test_requires_id(self) -> None:
        tracker = InflightTracker()
        with pytest.raises(ValueError):
            tracker.begin({"kind": "model", "threadId": "th1"})


# ═══════════════════════════════════════════════════════════════════════════════
# MigrationAdapter tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigrationAdapter:
    def test_session_key_to_thread_id_deterministic(self) -> None:
        a = session_key_to_thread_id("cli:direct")
        b = session_key_to_thread_id("cli:direct")
        assert a == b

    def test_different_sessions_different_threads(self) -> None:
        a = session_key_to_thread_id("cli:direct")
        b = session_key_to_thread_id("feishu:group_123")
        assert a != b

    def test_reverse_mapping(self) -> None:
        tid = session_key_to_thread_id("cli:direct")
        assert thread_id_to_session_key(tid) == "cli:direct"

    def test_unknown_reverse_returns_none(self) -> None:
        assert thread_id_to_session_key("nonexistent") is None

    def test_register_and_clear(self) -> None:
        register_mapping("custom", "thread_custom")
        assert session_key_to_thread_id("custom") == "thread_custom"
        assert thread_id_to_session_key("thread_custom") == "custom"
        clear_mapping("custom")
        assert thread_id_to_session_key("thread_custom") is None


# ═══════════════════════════════════════════════════════════════════════════════
# ThreadService tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreadService:
    @pytest.mark.asyncio
    async def test_create_thread(self, thread_svc: ThreadService) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        assert th["id"].startswith("thread_")
        assert th["workspace"] == "/tmp/ws"
        assert th["model"] == "deepseek-chat"
        assert th["mode"] == "agent"
        assert th["status"] == "idle"

    @pytest.mark.asyncio
    async def test_create_thread_emits_event(self, thread_svc: ThreadService, bus: EventBus) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        events_list = bus.history(th["id"])
        assert any(e["kind"] == "thread_created" for e in events_list)

    @pytest.mark.asyncio
    async def test_get_existing(self, thread_svc: ThreadService) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        loaded = await thread_svc.get(th["id"])
        assert loaded is not None
        assert loaded["id"] == th["id"]

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, thread_svc: ThreadService) -> None:
        assert await thread_svc.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list(self, thread_svc: ThreadService) -> None:
        await thread_svc.create(workspace="/tmp/ws", model="gpt")
        await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        threads = await thread_svc.list()
        assert len(threads) >= 2

    @pytest.mark.asyncio
    async def test_update(self, thread_svc: ThreadService, bus: EventBus) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        updated = await thread_svc.update(th["id"], {"title": "Updated Title", "status": "archived"})
        assert updated is not None
        assert updated["title"] == "Updated Title"
        assert updated["status"] == "archived"

        events_list = bus.history(th["id"])
        assert any(e["kind"] == "thread_updated" for e in events_list)

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, thread_svc: ThreadService) -> None:
        result = await thread_svc.update("nonexistent", {"title": "Nope"})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, thread_svc: ThreadService) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        assert await thread_svc.delete(th["id"]) is True
        assert await thread_svc.get(th["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, thread_svc: ThreadService) -> None:
        assert await thread_svc.delete("ghost") is False

    @pytest.mark.asyncio
    async def test_fork(self, thread_svc: ThreadService) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat", title="Original")
        forked = await thread_svc.fork(th["id"], title="Forked")
        assert forked["id"] != th["id"]
        assert forked["forkedFromThreadId"] == th["id"]
        assert forked["title"] == "Forked"
        assert forked["relation"] == "fork"
        assert forked["turns"] == []

    @pytest.mark.asyncio
    async def test_fork_nonexistent_raises(self, thread_svc: ThreadService) -> None:
        with pytest.raises(ValueError, match="not found"):
            await thread_svc.fork("nonexistent")


# ═══════════════════════════════════════════════════════════════════════════════
# TurnService tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTurnService:
    @pytest.mark.asyncio
    async def test_start_turn_creates_user_item(
        self, thread_svc: ThreadService, turn_svc: TurnService
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello world")
        assert result["threadId"] == th["id"]
        assert result["turnId"].startswith("turn_")
        assert result["userMessageItemId"].startswith("item_")

        turn = await turn_svc.get_turn(th["id"], result["turnId"])
        assert turn is not None
        assert turn["status"] == "running"
        assert turn["prompt"] == "hello world"

    @pytest.mark.asyncio
    async def test_start_turn_creates_abort_token(
        self, thread_svc: ThreadService, turn_svc: TurnService
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")
        token = turn_svc.get_abort_token(result["turnId"])
        assert token is not None
        assert not token.is_set()

    @pytest.mark.asyncio
    async def test_start_turn_emits_events(
        self, thread_svc: ThreadService, turn_svc: TurnService, bus: EventBus
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        await turn_svc.start_turn(th["id"], "hello")
        events_list = bus.history(th["id"])
        kinds = [e["kind"] for e in events_list]
        assert "turn_started" in kinds
        assert "item_created" in kinds

    @pytest.mark.asyncio
    async def test_start_turn_updates_thread_status(
        self, thread_svc: ThreadService, turn_svc: TurnService
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        assert th["status"] == "idle"
        await turn_svc.start_turn(th["id"], "hello")
        loaded = await thread_svc.get(th["id"])
        assert loaded is not None
        assert loaded["status"] == "running"

    @pytest.mark.asyncio
    async def test_finish_turn_completed(
        self, thread_svc: ThreadService, turn_svc: TurnService, bus: EventBus
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")
        await turn_svc.finish_turn(th["id"], result["turnId"], "completed")

        turn = await turn_svc.get_turn(th["id"], result["turnId"])
        assert turn is not None
        assert turn["status"] == "completed"
        assert turn["finishedAt"] is not None

        loaded = await thread_svc.get(th["id"])
        assert loaded is not None
        assert loaded["status"] == "idle"

        events_list = bus.history(th["id"])
        assert any(e["kind"] == "turn_completed" for e in events_list)

    @pytest.mark.asyncio
    async def test_finish_turn_failed(
        self, thread_svc: ThreadService, turn_svc: TurnService, bus: EventBus
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")
        await turn_svc.finish_turn(th["id"], result["turnId"], "failed", error="boom")

        turn = await turn_svc.get_turn(th["id"], result["turnId"])
        assert turn is not None
        assert turn["status"] == "failed"

        events_list = bus.history(th["id"])
        assert any(e["kind"] == "turn_failed" for e in events_list)

    @pytest.mark.asyncio
    async def test_interrupt_turn_aborts(
        self, thread_svc: ThreadService, turn_svc: TurnService
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")

        token = turn_svc.get_abort_token(result["turnId"])
        assert token is not None

        resp = await turn_svc.interrupt_turn(th["id"], result["turnId"])
        assert resp["status"] == "aborted"
        assert token.is_set()

        turn = await turn_svc.get_turn(th["id"], result["turnId"])
        assert turn is not None
        assert turn["status"] == "aborted"

    @pytest.mark.asyncio
    async def test_interrupt_turn_discard_preserves_user_item(
        self, thread_svc: ThreadService, turn_svc: TurnService, session_store: FileSessionStore
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")
        # Add an assistant item
        await turn_svc.apply_item(th["id"], {
            "id": "item_fake",
            "turnId": result["turnId"],
            "threadId": th["id"],
            "role": "assistant",
            "status": "completed",
            "kind": "assistant_text",
            "createdAt": FIXED_TIME,
            "text": "response",
        })
        await turn_svc.interrupt_turn(th["id"], result["turnId"], discard=True)

        items = await session_store.load_items(th["id"])
        # Only the user message should remain
        kinds = [i["kind"] for i in items]
        assert "user_message" in kinds
        assert "assistant_text" not in kinds

    @pytest.mark.asyncio
    async def test_steer_turn(
        self, thread_svc: ThreadService, turn_svc: TurnService, bus: EventBus
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")
        await turn_svc.steer_turn(th["id"], result["turnId"], "also check logs")

        events_list = bus.history(th["id"])
        assert any(e["kind"] == "turn_steered" for e in events_list)

        drained = turn_svc.drain_steering(th["id"])
        assert "also check logs" in drained

    @pytest.mark.asyncio
    async def test_drain_steering_clears(self, turn_svc: TurnService) -> None:
        turn_svc._steering["th1"] = ["msg1", "msg2"]
        drained = turn_svc.drain_steering("th1")
        assert drained == ["msg1", "msg2"]
        assert turn_svc.drain_steering("th1") == []  # cleared

    @pytest.mark.asyncio
    async def test_apply_item(
        self, thread_svc: ThreadService, turn_svc: TurnService, bus: EventBus
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")
        item = {
            "id": "item_tool_th1",
            "turnId": result["turnId"],
            "threadId": th["id"],
            "role": "assistant",
            "status": "completed",
            "kind": "tool_call",
            "createdAt": FIXED_TIME,
            "toolName": "read",
            "callId": "call_1",
            "toolKind": "tool_call",
            "arguments": {"path": "test.txt"},
        }
        await turn_svc.apply_item(th["id"], item)
        events_list = bus.history(th["id"])
        assert any(e["kind"] == "item_created" for e in events_list)

    @pytest.mark.asyncio
    async def test_update_item(
        self, thread_svc: ThreadService, turn_svc: TurnService, bus: EventBus
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")
        updated = await turn_svc.update_item(th["id"], result["userMessageItemId"], {
            "status": "aborted",
        })
        assert updated is not None
        assert updated["status"] == "aborted"

        events_list = bus.history(th["id"])
        assert any(e["kind"] == "item_updated" for e in events_list)

    @pytest.mark.asyncio
    async def test_get_turn_unknown(self, turn_svc: TurnService) -> None:
        assert await turn_svc.get_turn("nonexistent", "turn_x") is None

    @pytest.mark.asyncio
    async def test_abort_token_cleared_on_finish(
        self, thread_svc: ThreadService, turn_svc: TurnService
    ) -> None:
        th = await thread_svc.create(workspace="/tmp/ws", model="deepseek-chat")
        result = await turn_svc.start_turn(th["id"], "hello")
        assert turn_svc.get_abort_token(result["turnId"]) is not None
        await turn_svc.finish_turn(th["id"], result["turnId"], "completed")
        assert turn_svc.get_abort_token(result["turnId"]) is None
