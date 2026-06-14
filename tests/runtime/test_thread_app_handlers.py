"""Tests for Codex-style thread AppServer handlers."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.thread_app_handlers import register_codex_thread_handlers


# ── helpers ─────────────────────────────────────────────────────────────


def _make_mock_session(session_id: str):
    """Create a mock RuntimeSession with thread/ledger/replay services."""
    from miqi.runtime.thread_runtime import ThreadRuntime
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime
    from miqi.runtime.history_runtime import HistoryRuntime

    session = MagicMock()
    session.session_id = session_id

    # We need real runtimes that share a database
    db_path = session_id  # used as key later

    session.services = MagicMock()
    session.services.session_id = session_id
    session.stop = AsyncMock()
    session.stop_all = AsyncMock()

    return session


def _make_mock_session_with_real_runtimes(session_id: str, db_base: Path):
    """Create a mock session with real ThreadRuntime/LedgerRuntime/ReplayRuntime."""
    from miqi.runtime.thread_runtime import ThreadRuntime
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime
    from miqi.runtime.history_runtime import HistoryRuntime

    db_path = db_base / "runtime.db"
    threads = ThreadRuntime(db_path, session_id=session_id)
    ledger = LedgerRuntime(db_path, session_id=session_id)
    replay = ReplayRuntime(ledger)
    history = HistoryRuntime(db_path, session_id=session_id)

    session = MagicMock()
    session.session_id = session_id
    session.services = MagicMock()
    session.services.thread_runtime = threads
    session.services.ledger_runtime = ledger
    session.services.replay_runtime = replay
    session.services.history_runtime = history
    session.stop = AsyncMock()

    return session


# ── thread/start ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_start_creates_thread(tmp_path):
    session_id = "client-1:default"
    session = _make_mock_session_with_real_runtimes(session_id, tmp_path / "test_thread_start_creates_thread")
    await session.services.thread_runtime.initialize()
    await session.services.ledger_runtime.initialize()

    registry = ClientSessionRegistry()
    # Manually insert session to bypass create_session
    registry._sessions[session_id] = session
    registry._client_sessions.setdefault("client-1", set()).add(session_id)
    registry._session_clients.setdefault(session_id, set()).add("client-1")
    registry._last_activity[session_id] = 0

    server = AppServer(registry)
    register_codex_thread_handlers(server)

    response = await server.dispatch(
        "req-1", "thread/start",
        {"title": "Hello", "threadId": "thread-test-1"},
        "client-1", session_id,
    )

    assert "result" in response, f"Expected result but got: {response}"
    thread = response["result"]["thread"]
    assert thread["name"] == "Hello"
    assert thread["status"]["type"] == "idle"
    assert thread["id"] == "thread-test-1"

    await session.services.thread_runtime.close()
    await session.services.ledger_runtime.close()
    await registry.stop_all()


# ── thread/read ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_read_without_turns(tmp_path):
    session_id = "client-1:default"
    session = _make_mock_session_with_real_runtimes(session_id, tmp_path / "test_thread_read_without_turns")
    await session.services.thread_runtime.initialize()
    await session.services.ledger_runtime.initialize()

    await session.services.thread_runtime.create_thread(
        title="Read", thread_id="thread-read",
    )

    registry = ClientSessionRegistry()
    registry._sessions[session_id] = session
    registry._client_sessions.setdefault("client-1", set()).add(session_id)
    registry._session_clients.setdefault(session_id, set()).add("client-1")
    registry._last_activity[session_id] = 0

    server = AppServer(registry)
    register_codex_thread_handlers(server)

    response = await server.dispatch(
        "req-1", "thread/read",
        {"threadId": "thread-read"},
        "client-1", session_id,
    )
    assert response["result"]["thread"]["id"] == "thread-read"
    assert response["result"]["thread"]["turns"] == []

    await session.services.thread_runtime.close()
    await session.services.ledger_runtime.close()
    await registry.stop_all()


# ── thread/turns/items/list ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_turns_items_list_is_unsupported():
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_codex_thread_handlers(server)
    response = await server.dispatch(
        "req-1", "thread/turns/items/list",
        {"threadId": "t", "turnId": "x"},
        "client-1", None,
    )
    assert response["code"] == "UNSUPPORTED_METHOD"
    await registry.stop_all()


# ── thread/name/set ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_name_set_renames(tmp_path):
    session_id = "client-1:default"
    session = _make_mock_session_with_real_runtimes(session_id, tmp_path / "test_thread_name_set_renames")
    await session.services.thread_runtime.initialize()
    await session.services.ledger_runtime.initialize()

    await session.services.thread_runtime.create_thread(
        title="Old", thread_id="thread-rename-me",
    )

    registry = ClientSessionRegistry()
    registry._sessions[session_id] = session
    registry._client_sessions.setdefault("client-1", set()).add(session_id)
    registry._session_clients.setdefault(session_id, set()).add("client-1")
    registry._last_activity[session_id] = 0

    server = AppServer(registry)
    register_codex_thread_handlers(server)

    response = await server.dispatch(
        "req-1", "thread/name/set",
        {"threadId": "thread-rename-me", "name": "New Name"},
        "client-1", session_id,
    )
    assert response["result"]["thread"]["name"] == "New Name"

    await session.services.thread_runtime.close()
    await session.services.ledger_runtime.close()
    await registry.stop_all()


# ── thread/resume ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_resume_reads_existing_thread(tmp_path):
    session_id = "client-1:default"
    session = _make_mock_session_with_real_runtimes(session_id, tmp_path / "test_thread_resume_reads_existing_thread")
    await session.services.thread_runtime.initialize()
    await session.services.ledger_runtime.initialize()

    await session.services.thread_runtime.create_thread(
        title="Resumeable", thread_id="thread-resume-1",
    )

    registry = ClientSessionRegistry()
    registry._sessions[session_id] = session
    registry._client_sessions.setdefault("client-1", set()).add(session_id)
    registry._session_clients.setdefault(session_id, set()).add("client-1")
    registry._last_activity[session_id] = 0

    server = AppServer(registry)
    register_codex_thread_handlers(server)

    response = await server.dispatch(
        "req-1", "thread/resume",
        {"threadId": "thread-resume-1"},
        "client-1", session_id,
    )
    assert response["result"]["thread"]["name"] == "Resumeable"

    await session.services.thread_runtime.close()
    await session.services.ledger_runtime.close()
    await registry.stop_all()


# ── thread/loaded/list ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_loaded_list_returns_client_threads(tmp_path):
    session_id = "client-1:default"
    session = _make_mock_session_with_real_runtimes(session_id, tmp_path / "test_thread_loaded_list_returns_client_threads")
    await session.services.thread_runtime.initialize()
    await session.services.ledger_runtime.initialize()

    await session.services.thread_runtime.create_thread(
        title="Loaded", thread_id="loaded-1",
    )

    registry = ClientSessionRegistry()
    registry._sessions[session_id] = session
    registry._client_sessions.setdefault("client-1", set()).add(session_id)
    registry._session_clients.setdefault(session_id, set()).add("client-1")
    registry._last_activity[session_id] = 0

    server = AppServer(registry)
    register_codex_thread_handlers(server)

    response = await server.dispatch(
        "req-1", "thread/loaded/list", {},
        "client-1", None,
    )
    assert "loaded-1" in response["result"]["threadIds"]

    await session.services.thread_runtime.close()
    await session.services.ledger_runtime.close()
    await registry.stop_all()


# ── security: unauthorized access ────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_read_unauthorized():
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_codex_thread_handlers(server)
    response = await server.dispatch(
        "req-1", "thread/read",
        {"threadId": "nonexistent"},
        "client-1", "client-1:default",
    )
    assert response["code"] == "UNAUTHORIZED"
    await registry.stop_all()
