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


# ── Stored rollback and fork tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_rollback_works_on_stored_thread_without_live_session(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db)
    # Add a second turn directly
    ledger = LedgerRuntime(db, session_id="client-a:default")
    await ledger.initialize()
    try:
        await ledger.append_item(thread_id="thread-1", turn_id="turn-2", item_type="turn_started")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-2", item_type="message", role="user", content="drop")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-2", item_type="turn_completed")
    finally:
        await ledger.close()
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/rollback",
        {"threadId": "thread-1", "dropLastTurns": 1},
        "client-a",
        None,
    )
    turns = response["result"]["thread"]["turns"]
    assert [turn["id"] for turn in turns] == ["turn-1"]


@pytest.mark.asyncio
async def test_thread_fork_copies_stored_thread_without_live_session(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, thread_id="source")
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/fork",
        {"threadId": "source", "title": "Forked", "excludeTurns": False},
        "client-a",
        None,
    )
    thread = response["result"]["thread"]
    assert thread["forkedFromId"] == "source"
    assert thread["turns"][0]["id"] == "turn-1"


@pytest.mark.asyncio
async def test_thread_rollback_missing_thread_id_rejected(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/rollback", {"dropLastTurns": 1}, "client-a", None,
    )
    assert response["code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_thread_fork_missing_thread_id_rejected(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/fork", {}, "client-a", None,
    )
    assert response["code"] == "INVALID_PARAMS"


# ── Clean workspace (missing DB) tests ───────────────────────────────────


@pytest.mark.asyncio
async def test_thread_list_returns_empty_on_clean_workspace(tmp_path):
    """thread/list on a workspace with no runtime.db returns []."""
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/list", {}, "client-a", None,
    )
    assert response["result"]["data"] == []
    assert response["result"]["nextCursor"] is None


@pytest.mark.asyncio
async def test_thread_read_returns_not_found_on_clean_workspace(tmp_path):
    """thread/read on a workspace with no runtime.db returns NOT_FOUND."""
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/read", {"threadId": "thread-1"}, "client-a", None,
    )
    assert response["code"] == "NOT_FOUND"


# ── History (provider-visible messages) tests ────────────────────────────


@pytest.mark.asyncio
async def test_stored_fork_copies_history_rows(tmp_path):
    """Stored fork copies runtime_history_items so destination has provider messages."""
    from miqi.runtime.stored_runtime import StoredRuntimeReader
    from miqi.runtime.history_runtime import HistoryItem
    import time

    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, thread_id="src-fork")
    # Seed history for source thread
    reader = StoredRuntimeReader(db, client_id="client-a")
    await reader._write_history_items(
        "client-a:default", "src-fork",
        [HistoryItem(item_id="h1", thread_id="src-fork", turn_id="turn-1",
                     role="user", content="fork-src",
                     payload={}, created_at=time.time())],
    )
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/fork",
        {"threadId": "src-fork", "title": "Forked", "excludeTurns": False},
        "client-a", None,
    )
    child_id = response["result"]["thread"]["id"]
    msgs = await reader.load_provider_messages(
        await reader.resolve_thread(child_id),
    )
    assert len(msgs) >= 1
    assert msgs[0]["content"] == "fork-src"


@pytest.mark.asyncio
async def test_stored_rollback_deletes_history_for_removed_turns(tmp_path):
    """Stored rollback removes history items belonging to dropped turns."""
    from miqi.runtime.stored_runtime import StoredRuntimeReader
    from miqi.runtime.history_runtime import HistoryItem
    import time

    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, thread_id="rollback-hist")
    reader = StoredRuntimeReader(db, client_id="client-a")
    # Two turns worth of history
    await reader._write_history_items(
        "client-a:default", "rollback-hist",
        [
            HistoryItem(item_id="h1", thread_id="rollback-hist", turn_id="turn-1",
                        role="user", content="keep", payload={}, created_at=time.time()),
            HistoryItem(item_id="h2", thread_id="rollback-hist", turn_id="turn-2",
                        role="user", content="drop", payload={}, created_at=time.time()),
        ],
    )
    # Add a second turn to the ledger
    from miqi.runtime.ledger_runtime import LedgerRuntime
    ledger = LedgerRuntime(db, session_id="client-a:default")
    await ledger.initialize()
    try:
        await ledger.append_item(thread_id="rollback-hist", turn_id="turn-2", item_type="turn_started")
        await ledger.append_item(thread_id="rollback-hist", turn_id="turn-2", item_type="message", role="user", content="drop")
        await ledger.append_item(thread_id="rollback-hist", turn_id="turn-2", item_type="turn_completed")
    finally:
        await ledger.close()
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/rollback",
        {"threadId": "rollback-hist", "dropLastTurns": 1},
        "client-a", None,
    )
    assert response["result"]["thread"]["turns"][0]["id"] == "turn-1"
    # History for turn-2 should be gone
    msgs = await reader.load_provider_messages(
        await reader.resolve_thread("rollback-hist"),
    )
    assert len(msgs) == 1
    assert msgs[0]["content"] == "keep"
