from __future__ import annotations

import pytest

from tests.runtime.test_thread_stored_handlers import _seed_thread, _server


@pytest.mark.asyncio
async def test_thread_export_returns_versioned_document(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db)
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/export", {"threadId": "thread-1"}, "client-a", None,
    )
    doc = response["result"]["document"]
    assert doc["version"] == 1
    assert doc["thread"]["thread_id"] == "thread-1"
    assert any(item["itemType"] == "message" for item in doc["ledgerItems"])


@pytest.mark.asyncio
async def test_thread_export_rejects_foreign_thread(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, session_id="client-b:default", thread_id="thread-b")
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/export", {"threadId": "thread-b"}, "client-a", None,
    )
    assert response["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_thread_export_missing_thread_id_rejected(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/export", {}, "client-a", None,
    )
    assert response["code"] == "INVALID_PARAMS"


# ── Import tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_import_round_trips_exported_document(tmp_path):
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, thread_id="source")
    server = _server(tmp_path)
    exported = await server.dispatch(
        "1", "thread/export", {"threadId": "source"}, "client-a", None,
    )
    doc = exported["result"]["document"]
    imported = await server.dispatch(
        "2", "thread/import",
        {"document": doc, "threadId": "imported", "includeTurns": True},
        "client-a",
        None,
    )
    thread = imported["result"]["thread"]
    assert thread["id"] == "imported"
    assert thread["turns"][0]["id"] == "turn-1"


@pytest.mark.asyncio
async def test_thread_import_rejects_foreign_session_id(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/import",
        {"sessionId": "client-b:default", "document": {"version": 1, "thread": {"thread_id": "x"}, "ledgerItems": []}},
        "client-a",
        None,
    )
    assert response["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_thread_import_rejects_bad_version(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/import",
        {"document": {"version": 999, "thread": {"thread_id": "x"}, "ledgerItems": []}},
        "client-a",
        None,
    )
    assert response["code"] == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_thread_import_missing_document_rejected(tmp_path):
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/import", {}, "client-a", None,
    )
    assert response["code"] == "INVALID_PARAMS"


# ── Clean workspace tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_import_creates_db_and_table_on_clean_workspace(tmp_path):
    """thread/import on clean workspace creates runtime.db and tables, then thread/read works."""
    server = _server(tmp_path)
    document = {
        "version": 1,
        "thread": {
            "thread_id": "imported-clean",
            "title": "From clean workspace",
            "status": "active",
            "created_at": 1000.0,
            "updated_at": 1000.0,
        },
        "ledgerItems": [
            {
                "itemType": "turn_started",
                "turnId": "turn-1",
                "seq": 1,
                "role": None,
                "content": "",
                "payload": {},
                "createdAt": 1000.0,
            },
            {
                "itemType": "message",
                "turnId": "turn-1",
                "seq": 2,
                "role": "user",
                "content": "hello from clean",
                "payload": {},
                "createdAt": 1000.1,
            },
        ],
        "providerMessages": [],
    }
    # Import should create the DB and tables
    imported = await server.dispatch(
        "1", "thread/import",
        {"document": document, "includeTurns": True},
        "client-a",
        None,
    )
    assert imported["result"]["thread"]["id"] == "imported-clean"
    # Verify the DB file was created
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    assert db.exists()
    # thread/read should now find it
    read = await server.dispatch(
        "2", "thread/read",
        {"threadId": "imported-clean", "includeTurns": True},
        "client-a",
        None,
    )
    assert read["result"]["thread"]["id"] == "imported-clean"
