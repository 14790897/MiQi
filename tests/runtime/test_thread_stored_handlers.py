from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from miqi.config.schema import Config
from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.ledger_runtime import LedgerRuntime
from miqi.runtime.thread_app_handlers import register_codex_thread_handlers
from miqi.runtime.thread_runtime import ThreadRuntime


async def _seed_thread(db_path, session_id="client-a:default", thread_id="thread-1"):
    threads = ThreadRuntime(db_path, session_id=session_id)
    ledger = LedgerRuntime(db_path, session_id=session_id)
    await threads.initialize()
    await ledger.initialize()
    await threads.create_thread(title="Stored thread", thread_id=thread_id)
    await ledger.append_item(thread_id=thread_id, turn_id="turn-1", item_type="turn_started")
    await ledger.append_item(thread_id=thread_id, turn_id="turn-1", item_type="message", role="user", content="hello")
    await ledger.append_item(thread_id=thread_id, turn_id="turn-1", item_type="assistant_delta", content="hi")
    await ledger.append_item(thread_id=thread_id, turn_id="turn-1", item_type="turn_completed")
    await ledger.close()
    await threads.close()


def _server(tmp_path):
    registry = ClientSessionRegistry()
    cfg = Config()
    cfg.agents.defaults.workspace = str(tmp_path)
    state = MagicMock()
    state.load_config.return_value = cfg
    registry.bridge_context["state"] = state
    server = AppServer(registry)
    register_codex_thread_handlers(server)
    return server


@pytest.mark.asyncio
async def test_thread_read_reads_stored_thread_without_live_session(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db)
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/read",
        {"threadId": "thread-1", "includeTurns": True},
        "client-a",
        None,
    )
    thread = response["result"]["thread"]
    assert thread["id"] == "thread-1"
    assert thread["status"] == {"type": "notLoaded"}
    assert thread["turns"][0]["items"][0]["type"] == "userMessage"


@pytest.mark.asyncio
async def test_thread_turns_list_reads_stored_turns_without_live_session(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db)
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/turns/list",
        {"threadId": "thread-1", "limit": 10, "sortDirection": "asc"},
        "client-a",
        None,
    )
    assert response["result"]["data"][0]["id"] == "turn-1"


@pytest.mark.asyncio
async def test_thread_list_pages_stored_threads(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, thread_id="thread-1")
    await _seed_thread(db, thread_id="thread-2")
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/list", {"limit": 1}, "client-a", None,
    )
    assert len(response["result"]["data"]) == 1
    assert response["result"]["nextCursor"] is not None


@pytest.mark.asyncio
async def test_thread_read_rejects_foreign_stored_thread(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, session_id="client-b:default", thread_id="thread-b")
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/read", {"threadId": "thread-b"}, "client-a", None,
    )
    assert response["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_thread_read_ambiguous_thread_requires_session_id(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, session_id="client-a:one", thread_id="same")
    await _seed_thread(db, session_id="client-a:two", thread_id="same")
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/read", {"threadId": "same"}, "client-a", None,
    )
    assert response["code"] == "AMBIGUOUS_THREAD"


@pytest.mark.asyncio
async def test_thread_read_missing_thread_id_rejected(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/read", {}, "client-a", None,
    )
    assert response["code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_thread_turns_list_missing_thread_id_rejected(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/turns/list", {}, "client-a", None,
    )
    assert response["code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_thread_turns_items_list_still_unsupported(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/turns/items/list", {"threadId": "x"}, "client-a", None,
    )
    assert response["code"] == "UNSUPPORTED_METHOD"
