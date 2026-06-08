"""Phase 9 tests — KunRuntime composition root, Auth, full lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from miqi.kun_runtime.auth import BearerTokenAuth
from miqi.kun_runtime.runtime import KunRuntime, RuntimeOptions
from miqi.kun_runtime.model_client import FakeModelClient
from miqi.kun_runtime.tool_host import FakeToolHost


FIXED_TIME = "2026-06-08T12:00:00Z"


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    return tmp_path / "kun_data"


@pytest.fixture
def runtime_opts(tmp_data_dir: Path) -> RuntimeOptions:
    return RuntimeOptions(
        data_dir=tmp_data_dir,
        workspace="/tmp/test_ws",
        model="fake-model",
    )


@pytest.fixture
def runtime(runtime_opts: RuntimeOptions) -> KunRuntime:
    rt = KunRuntime(runtime_opts)
    # Wire fake components for testing
    rt.model = FakeModelClient(text_chunks=["Hello from runtime!"])
    rt.tool_host = FakeToolHost(
        tools=[{"name": "read", "description": "Read", "inputSchema": {}, "toolKind": "tool_call"}],
        results={"read": "file contents"},
    )
    rt.events._now_iso = lambda: FIXED_TIME
    return rt


class TestBearerTokenAuth:
    def test_insecure_allows_all(self) -> None:
        auth = BearerTokenAuth(token="test", insecure=True)
        assert auth.verify(None) is True
        assert auth.verify("") is True
        assert auth.verify("anything") is True

    def test_secure_rejects_empty(self) -> None:
        auth = BearerTokenAuth(token="secret", insecure=False)
        assert auth.verify(None) is False
        assert auth.verify("") is False

    def test_secure_validates_bearer(self) -> None:
        auth = BearerTokenAuth(token="secret", insecure=False)
        assert auth.verify("Bearer not-secret") is False
        assert auth.verify("Bearer secret") is True

    def test_extract_bearer(self) -> None:
        assert BearerTokenAuth.extract_bearer({"authorization": "Bearer abc"}) == "abc"
        assert BearerTokenAuth.extract_bearer({"Authorization": "Bearer abc"}) == "abc"
        assert BearerTokenAuth.extract_bearer(None) is None


class TestRuntimeComposition:
    def test_info(self, runtime: KunRuntime) -> None:
        info = runtime.info()
        assert info["model"] == "fake-model"
        assert info["port"] == 9876
        assert isinstance(info["dataDir"], str)

    def test_missing_model_raises_on_loop_access(self, runtime_opts: RuntimeOptions) -> None:
        rt = KunRuntime(runtime_opts)
        with pytest.raises(RuntimeError, match="not configured"):
            _ = rt.loop

    def test_missing_tool_host_raises_on_loop_access(self, runtime_opts: RuntimeOptions) -> None:
        rt = KunRuntime(runtime_opts)
        rt.model = FakeModelClient()
        with pytest.raises(RuntimeError, match="not configured"):
            _ = rt.loop


class TestRuntimeEndToEnd:
    @pytest.mark.asyncio
    async def test_full_turn_lifecycle(self, runtime: KunRuntime) -> None:
        """End-to-end: create thread → start turn → run → check events."""
        # Create thread
        th = await runtime.threads.create(workspace="/tmp/ws", model="fake-model")
        thread_id = th["id"]

        # Start turn
        result = await runtime.turns.start_turn(thread_id, "Hello, KUN!")
        turn_id = result["turnId"]

        # Run the loop
        status = await runtime.run_turn(thread_id, turn_id)
        assert status == "completed"

        # Check turn finished
        turn = await runtime.turns.get_turn(thread_id, turn_id)
        assert turn is not None
        assert turn["status"] == "completed"

        # Check events replayable
        events_list = runtime.event_bus.history(thread_id)
        kinds = [e["kind"] for e in events_list]
        assert "turn_started" in kinds
        assert "turn_completed" in kinds

    @pytest.mark.asyncio
    async def test_multiple_turns_same_thread(self, runtime: KunRuntime) -> None:
        th = await runtime.threads.create(workspace="/tmp/ws", model="fake-model")
        thread_id = th["id"]

        # Turn 1
        r1 = await runtime.turns.start_turn(thread_id, "First message")
        await runtime.run_turn(thread_id, r1["turnId"])

        # Turn 2
        r2 = await runtime.turns.start_turn(thread_id, "Second message")
        await runtime.run_turn(thread_id, r2["turnId"])

        # Both turns recorded
        thread = await runtime.threads.get(thread_id)
        assert thread is not None
        assert len(thread.get("turns", [])) >= 2

    @pytest.mark.asyncio
    async def test_thread_listing(self, runtime: KunRuntime) -> None:
        await runtime.threads.create(workspace="/tmp/ws", model="fake-model", title="Thread A")
        await runtime.threads.create(workspace="/tmp/ws", model="fake-model", title="Thread B")

        threads = await runtime.threads.list()
        titles = [t["title"] for t in threads]
        assert "Thread A" in titles
        assert "Thread B" in titles

    @pytest.mark.asyncio
    async def test_events_since_seq(self, runtime: KunRuntime) -> None:
        th = await runtime.threads.create(workspace="/tmp/ws", model="fake-model")
        thread_id = th["id"]

        r = await runtime.turns.start_turn(thread_id, "hello")
        await runtime.run_turn(thread_id, r["turnId"])

        # Replay from seq 2
        events_since = runtime.event_bus.history(thread_id, since_seq=2)
        assert len(events_since) > 0
        for e in events_since:
            assert e.get("seq", 0) > 2
