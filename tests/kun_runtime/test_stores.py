"""Phase 3 tests — FileThreadStore, FileSessionStore, UsageService."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from miqi.kun_runtime.stores import FileSessionStore, FileThreadStore
from miqi.kun_runtime.usage import UsageService


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_store_dir(tmp_path: Path) -> Path:
    """Isolated store directory — must be tmp_path for all tests."""
    return tmp_path / "kun_data"


@pytest.fixture
def thread_store(tmp_store_dir: Path) -> FileThreadStore:
    return FileThreadStore(tmp_store_dir)


@pytest.fixture
def session_store(tmp_store_dir: Path) -> FileSessionStore:
    return FileSessionStore(tmp_store_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# FileThreadStore tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileThreadStore:
    @pytest.mark.asyncio
    async def test_get_returns_none_for_unknown(self, thread_store: FileThreadStore) -> None:
        assert await thread_store.get("no_such_thread") is None

    @pytest.mark.asyncio
    async def test_upsert_and_get(self, thread_store: FileThreadStore) -> None:
        record = {
            "id": "th1",
            "title": "Test",
            "workspace": "/tmp/ws",
            "model": "deepseek-chat",
            "mode": "agent",
            "status": "idle",
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
        await thread_store.upsert(record)
        loaded = await thread_store.get("th1")
        assert loaded is not None
        assert loaded["id"] == "th1"
        assert loaded["title"] == "Test"

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, thread_store: FileThreadStore) -> None:
        await thread_store.upsert({
            "id": "th1", "title": "Old", "workspace": "/ws",
            "model": "gpt", "mode": "agent", "status": "idle",
            "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
        })
        await thread_store.upsert({
            "id": "th1", "title": "New", "workspace": "/ws",
            "model": "gpt", "mode": "agent", "status": "archived",
            "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-02T00:00:00Z",
        })
        loaded = await thread_store.get("th1")
        assert loaded is not None
        assert loaded["title"] == "New"
        assert loaded["status"] == "archived"

    @pytest.mark.asyncio
    async def test_upsert_requires_id(self, thread_store: FileThreadStore) -> None:
        with pytest.raises(ValueError, match="id"):
            await thread_store.upsert({"title": "no id"})

    @pytest.mark.asyncio
    async def test_delete(self, thread_store: FileThreadStore) -> None:
        await thread_store.upsert({
            "id": "th1", "title": "T", "workspace": "/ws",
            "model": "gpt", "mode": "agent", "status": "idle",
            "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
        })
        assert await thread_store.delete("th1") is True
        assert await thread_store.get("th1") is None

    @pytest.mark.asyncio
    async def test_delete_unknown_returns_false(self, thread_store: FileThreadStore) -> None:
        assert await thread_store.delete("ghost") is False

    @pytest.mark.asyncio
    async def test_list(self, thread_store: FileThreadStore) -> None:
        await thread_store.upsert({
            "id": "th_a", "title": "A", "workspace": "/ws",
            "model": "gpt", "mode": "agent", "status": "idle",
            "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
        })
        await asyncio.sleep(0.01)  # ensure mtime ordering
        await thread_store.upsert({
            "id": "th_b", "title": "B", "workspace": "/ws",
            "model": "gpt", "mode": "agent", "status": "idle",
            "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-02T00:00:00Z",
        })
        result = await thread_store.list()
        assert len(result) >= 2
        ids = [r["id"] for r in result]
        assert "th_a" in ids
        assert "th_b" in ids

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self, tmp_store_dir: Path) -> None:
        store1 = FileThreadStore(tmp_store_dir)
        await store1.upsert({
            "id": "th1", "title": "Persist", "workspace": "/ws",
            "model": "gpt", "mode": "agent", "status": "idle",
            "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
        })

        store2 = FileThreadStore(tmp_store_dir)
        loaded = await store2.get("th1")
        assert loaded is not None
        assert loaded["title"] == "Persist"


# ═══════════════════════════════════════════════════════════════════════════════
# FileSessionStore — items
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileSessionStoreItems:
    @pytest.mark.asyncio
    async def test_load_empty(self, session_store: FileSessionStore) -> None:
        items = await session_store.load_items("th1")
        assert items == []

    @pytest.mark.asyncio
    async def test_append_and_load(self, session_store: FileSessionStore) -> None:
        item = {
            "id": "item_1",
            "turnId": "t1",
            "threadId": "th1",
            "role": "user",
            "status": "completed",
            "kind": "user_message",
            "createdAt": "2026-01-01T00:00:00Z",
            "text": "hello",
        }
        await session_store.append_item("th1", item)
        items = await session_store.load_items("th1")
        assert len(items) == 1
        assert items[0]["id"] == "item_1"

    @pytest.mark.asyncio
    async def test_append_order_preserved(self, session_store: FileSessionStore) -> None:
        for i in range(5):
            await session_store.append_item("th1", {
                "id": f"item_{i}", "turnId": "t1", "threadId": "th1",
                "role": "user", "status": "completed",
                "kind": "user_message", "createdAt": "2026-01-01T00:00:00Z",
                "text": f"msg {i}",
            })
        items = await session_store.load_items("th1")
        assert len(items) == 5
        assert [it["id"] for it in items] == [f"item_{i}" for i in range(5)]

    @pytest.mark.asyncio
    async def test_update_item(self, session_store: FileSessionStore) -> None:
        await session_store.append_item("th1", {
            "id": "item_1", "turnId": "t1", "threadId": "th1",
            "role": "user", "status": "pending", "kind": "user_message",
            "createdAt": "2026-01-01T00:00:00Z", "text": "hello",
        })
        updated = await session_store.update_item("th1", "item_1", {
            "status": "completed", "finishedAt": "2026-01-01T00:01:00Z",
        })
        assert updated is not None
        assert updated["status"] == "completed"
        assert updated.get("finishedAt") == "2026-01-01T00:01:00Z"

        # Verify persistence
        items = await session_store.load_items("th1")
        assert items[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_update_item_unknown_returns_none(self, session_store: FileSessionStore) -> None:
        updated = await session_store.update_item("th1", "ghost", {"status": "completed"})
        assert updated is None

    @pytest.mark.asyncio
    async def test_rewrite_items(self, session_store: FileSessionStore) -> None:
        # Append 3 items
        for i in range(3):
            await session_store.append_item("th1", {
                "id": f"item_{i}", "turnId": "t1", "threadId": "th1",
                "role": "user", "status": "completed",
                "kind": "user_message", "createdAt": "2026-01-01T00:00:00Z",
                "text": f"msg {i}",
            })
        # Rewrite with only 2 items
        new_items = [
            {"id": "item_a", "turnId": "t1", "threadId": "th1",
             "role": "user", "status": "completed", "kind": "user_message",
             "createdAt": "2026-01-01T00:00:00Z", "text": "kept 1"},
            {"id": "item_b", "turnId": "t1", "threadId": "th1",
             "role": "assistant", "status": "completed", "kind": "assistant_text",
             "createdAt": "2026-01-01T00:01:00Z", "text": "kept 2"},
        ]
        await session_store.rewrite_items("th1", new_items)
        items = await session_store.load_items("th1")
        assert len(items) == 2
        assert items[0]["id"] == "item_a"
        assert items[1]["id"] == "item_b"

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self, tmp_store_dir: Path) -> None:
        store1 = FileSessionStore(tmp_store_dir)
        await store1.append_item("th1", {
            "id": "item_persist", "turnId": "t1", "threadId": "th1",
            "role": "user", "status": "completed", "kind": "user_message",
            "createdAt": "2026-01-01T00:00:00Z", "text": "persist me",
        })

        store2 = FileSessionStore(tmp_store_dir)
        items = await store2.load_items("th1")
        assert len(items) == 1
        assert items[0]["id"] == "item_persist"

    @pytest.mark.asyncio
    async def test_isolation_between_threads(self, session_store: FileSessionStore) -> None:
        await session_store.append_item("th1", {
            "id": "i1", "turnId": "t1", "threadId": "th1",
            "role": "user", "status": "completed", "kind": "user_message",
            "createdAt": "2026-01-01T00:00:00Z", "text": "thread 1",
        })
        await session_store.append_item("th2", {
            "id": "i2", "turnId": "t2", "threadId": "th2",
            "role": "user", "status": "completed", "kind": "user_message",
            "createdAt": "2026-01-01T00:00:00Z", "text": "thread 2",
        })
        assert len(await session_store.load_items("th1")) == 1
        assert len(await session_store.load_items("th2")) == 1

    @pytest.mark.asyncio
    async def test_handles_corrupt_lines_gracefully(self, session_store: FileSessionStore) -> None:
        await session_store.append_item("th1", {
            "id": "good", "turnId": "t1", "threadId": "th1",
            "role": "user", "status": "completed", "kind": "user_message",
            "createdAt": "2026-01-01T00:00:00Z", "text": "good",
        })
        # Write a corrupt line directly
        items_path = session_store._items_path("th1")
        with open(items_path, "a", encoding="utf-8") as f:
            f.write("not valid json!!!\n")
        await session_store.append_item("th1", {
            "id": "also_good", "turnId": "t1", "threadId": "th1",
            "role": "user", "status": "completed", "kind": "user_message",
            "createdAt": "2026-01-01T00:00:00Z", "text": "also good",
        })
        items = await session_store.load_items("th1")
        assert len(items) == 2
        assert items[0]["id"] == "good"
        assert items[1]["id"] == "also_good"


# ═══════════════════════════════════════════════════════════════════════════════
# FileSessionStore — events
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileSessionStoreEvents:
    @pytest.mark.asyncio
    async def test_append_and_load_events(self, session_store: FileSessionStore) -> None:
        await session_store.append_event("th1", {"seq": 1, "kind": "turn_started", "threadId": "th1"})
        await session_store.append_event("th1", {"seq": 2, "kind": "turn_completed", "threadId": "th1"})
        events = await session_store.load_events_since("th1", since_seq=0)
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_load_events_since_seq(self, session_store: FileSessionStore) -> None:
        for i in range(1, 6):
            await session_store.append_event("th1", {"seq": i, "kind": "event", "threadId": "th1"})
        events = await session_store.load_events_since("th1", since_seq=3)
        assert len(events) == 2
        seqs = [e["seq"] for e in events]
        assert seqs == [4, 5]

    @pytest.mark.asyncio
    async def test_load_events_empty(self, session_store: FileSessionStore) -> None:
        events = await session_store.load_events_since("ghost")
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════════
# UsageService tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUsageService:
    def test_initial_for_thread_empty(self) -> None:
        svc = UsageService()
        assert svc.for_thread("th1") == {}

    def test_record_accumulates(self) -> None:
        svc = UsageService()
        svc.record("th1", {"promptTokens": 100, "completionTokens": 50, "totalTokens": 150, "costUsd": 0.0003})
        svc.record("th1", {"promptTokens": 200, "completionTokens": 100, "totalTokens": 300, "costUsd": 0.0006})
        snap = svc.for_thread("th1")
        assert snap["promptTokens"] == 300
        assert snap["completionTokens"] == 150
        assert snap["totalTokens"] == 450
        assert snap["costUsd"] == pytest.approx(0.0009)

    def test_threads_are_independent(self) -> None:
        svc = UsageService()
        svc.record("th1", {"promptTokens": 100, "completionTokens": 50, "totalTokens": 150})
        svc.record("th2", {"promptTokens": 500, "completionTokens": 300, "totalTokens": 800})
        assert svc.for_thread("th1")["promptTokens"] == 100
        assert svc.for_thread("th2")["promptTokens"] == 500

    def test_record_token_economy_savings(self) -> None:
        svc = UsageService()
        svc.record("th1", {"promptTokens": 1000, "completionTokens": 500, "totalTokens": 1500})
        svc.record_token_economy_savings("th1", {
            "tokenEconomySavingsTokens": 200,
            "tokenEconomySavingsUsd": 0.0004,
        })
        snap = svc.for_thread("th1")
        assert snap["promptTokens"] == 1000  # unchanged
        assert snap["tokenEconomySavingsTokens"] == 200

    def test_seed_thread(self) -> None:
        svc = UsageService()
        svc.seed_thread("th1", {"promptTokens": 9999, "completionTokens": 1, "totalTokens": 10000, "costUsd": 1.0})
        assert svc.for_thread("th1")["promptTokens"] == 9999

    def test_reset(self) -> None:
        svc = UsageService()
        svc.record("th1", {"promptTokens": 100, "completionTokens": 0, "totalTokens": 100})
        svc.reset("th1")
        assert svc.for_thread("th1") == {}
