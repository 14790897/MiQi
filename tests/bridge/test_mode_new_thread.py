"""#680 跟进：新会话（新 thread）首条消息的 reasoning mode 持久化。

用户反馈"切换深度后下一个会话还是极速"——根因：新 thread 不存在时
bridge 不写 metadata.mode，runtime 回退默认 fast。修复后 thread 不存在
也会 ensure+upsert 写入 mode。
"""
import asyncio
from types import SimpleNamespace

import pytest

from miqi.bridge.loop import BridgeRuntimeLoop


class FakeThreadStore:
    def __init__(self):
        self._d: dict[str, dict] = {}

    async def get(self, thread_id: str) -> dict | None:
        return self._d.get(thread_id)

    async def upsert(self, record: dict) -> None:
        self._d[record["id"]] = record


class FakeRuntime:
    def __init__(self, thread_store):
        self.thread_store = thread_store

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
async def test_new_thread_send_persists_mode(tmp_path):
    """新 thread（不存在）→ chat.send(reasoning_mode='think') →
    thread 记录被创建且 metadata.mode == 'think'（不再回退默认 fast）。"""
    store = FakeThreadStore()
    registry = FakeRegistry(FakeRuntime(store))
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

    thread = await store.get("t1")
    assert thread is not None, "thread 应被创建"
    assert (thread.get("metadata") or {}).get("mode") == "think", (
        f"新会话模式丢失：metadata.mode={(thread.get('metadata') or {}).get('mode')!r}"
    )


@pytest.mark.asyncio
async def test_existing_thread_mode_updated(tmp_path):
    """已有 thread（mode=fast）→ send think → 更新为 think（切模式生效）。"""
    store = FakeThreadStore()
    await store.upsert({"id": "t2", "turns": [], "metadata": {"mode": "fast"}})
    registry = FakeRegistry(FakeRuntime(store))
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

    thread = await store.get("t2")
    assert (thread.get("metadata") or {}).get("mode") == "think"
