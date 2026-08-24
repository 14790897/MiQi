"""#680 跟进：新会话（新 thread）首条消息的 reasoning mode 持久化。

外部审阅 2026-08-24 指出：RuntimeSession 无 thread_store（AttributeError 被
吞），mode 从不落盘——bridge 改为写 services.thread_runtime（SQLite
ThreadRuntime）。本测试用真实 ThreadRuntime（临时 SQLite）走 handler 验证
新 thread 创建 + metadata 写入（修审阅 P1：补真实链路集成测试）。
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from miqi.bridge.loop import BridgeRuntimeLoop
from miqi.runtime.thread_runtime import ThreadRuntime


class FakeRuntime:
    def __init__(self, thread_runtime):
        self.services = SimpleNamespace(thread_runtime=thread_runtime)

    async def submit(self, *args, **kwargs):
        pass


class FakeRegistry:
    def __init__(self, runtime):
        self._runtime = runtime

    async def get_session(self, client_id, runtime_id):
        return self._runtime


def _make_loop() -> BridgeRuntimeLoop:
    loop = BridgeRuntimeLoop(
        send_func=lambda *a, **k: None,
        dispatch_legacy_func=lambda *a, **k: None,
        dev_mode=False,
    )
    loop._session_drain_tasks = {}
    loop._app_server = SimpleNamespace(
        subscribe=lambda *a, **k: None,
        emit_event=lambda *a, **k: None,
    )
    return loop


@pytest.mark.asyncio
async def test_new_thread_send_persists_mode(tmp_path: Path):
    """新 thread（不存在）→ chat.send(reasoning_mode='think') →
    SQLite 中创建 thread 且 metadata.mode == 'think'（真实 ThreadRuntime）。"""
    thread_runtime = ThreadRuntime(tmp_path / "runtime.db", session_id="s1")
    await thread_runtime.initialize()
    registry = FakeRegistry(FakeRuntime(thread_runtime))
    loop = _make_loop()

    await loop._chat_send_handler(
        request_id="r1",
        params={
            "session_key": "s1",
            "thread_id": "t1",
            "content": "新会话模式测试",
            "reasoning_mode": "think",
        },
        client_id="c1",
        session_id=None,
        registry=registry,
    )

    thread = await thread_runtime.get_thread("t1")
    assert thread is not None, "thread 应被创建"
    assert thread.metadata.get("mode") == "think", (
        f"新会话模式丢失：metadata.mode={thread.metadata.get('mode')!r}"
    )


@pytest.mark.asyncio
async def test_existing_thread_mode_updated(tmp_path: Path):
    """已有 thread（mode=fast）→ send think → 更新为 think。"""
    thread_runtime = ThreadRuntime(tmp_path / "runtime.db", session_id="s1")
    await thread_runtime.initialize()
    await thread_runtime.create_thread(title="t2", thread_id="t2")
    await thread_runtime.update_metadata("t2", {"mode": "fast"})
    registry = FakeRegistry(FakeRuntime(thread_runtime))
    loop = _make_loop()

    await loop._chat_send_handler(
        request_id="r2",
        params={
            "session_key": "s1",
            "thread_id": "t2",
            "content": "切深度发送",
            "reasoning_mode": "think",
        },
        client_id="c1",
        session_id=None,
        registry=registry,
    )

    thread = await thread_runtime.get_thread("t2")
    assert thread.metadata.get("mode") == "think"
