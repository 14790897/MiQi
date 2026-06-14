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


# ── History (provider-visible messages) tests ─────────────────────────────


@pytest.mark.asyncio
async def test_export_includes_provider_messages(tmp_path):
    """thread/export includes non-empty providerMessages from stored history."""
    from miqi.runtime.stored_runtime import StoredRuntimeReader
    from miqi.runtime.history_runtime import HistoryItem

    db = tmp_path / ".miqi-runtime" / "runtime.db"
    await _seed_thread(db, thread_id="export-me")
    # Write some history items directly
    import time
    reader = StoredRuntimeReader(db, client_id="client-a")
    await reader._ensure_schema()
    await reader._write_history_items(
        "client-a:default", "export-me",
        [
            HistoryItem(item_id="h1", thread_id="export-me", turn_id="turn-1",
                        role="user", content="hello export",
                        payload={}, created_at=time.time()),
            HistoryItem(item_id="h2", thread_id="export-me", turn_id="turn-1",
                        role="assistant", content="hi there",
                        payload={"message_fields": {"name": "claude"}},
                        created_at=time.time()),
        ],
    )
    server = _server(tmp_path)
    response = await server.dispatch(
        "1", "thread/export", {"threadId": "export-me"}, "client-a", None,
    )
    doc = response["result"]["document"]
    assert len(doc["providerMessages"]) == 2
    assert doc["providerMessages"][0]["role"] == "user"
    assert doc["providerMessages"][1]["role"] == "assistant"
    assert doc["providerMessages"][1]["name"] == "claude"


@pytest.mark.asyncio
async def test_import_writes_provider_visible_history(tmp_path):
    """Import creates runtime_history_items readable via StoredRuntimeReader."""
    from miqi.runtime.stored_runtime import StoredRuntimeReader

    server = _server(tmp_path)
    document = {
        "version": 1,
        "thread": {"thread_id": "hist-1", "title": "H", "status": "active",
                    "created_at": 1.0, "updated_at": 1.0},
        "ledgerItems": [
            {"itemType": "message", "turnId": "turn-1", "seq": 1, "role": "user",
             "content": "p1", "payload": {}, "createdAt": 1.0},
            {"itemType": "message", "turnId": "turn-1", "seq": 2, "role": "assistant",
             "content": "p2", "payload": {}, "createdAt": 1.1},
        ],
        "providerMessages": [],
    }
    await server.dispatch(
        "1", "thread/import", {"document": document, "includeTurns": True},
        "client-a", None,
    )
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    reader = StoredRuntimeReader(db, client_id="client-a")
    msgs = await reader.load_provider_messages(
        await reader.resolve_thread("hist-1"),
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "p1"


@pytest.mark.asyncio
async def test_import_overwrite_deletes_stale_history(tmp_path):
    """Overwrite import removes old runtime_history_items so no stale context remains."""
    from miqi.runtime.stored_runtime import StoredRuntimeReader
    from miqi.runtime.history_runtime import HistoryItem
    import time

    server = _server(tmp_path)
    db = tmp_path / ".miqi-runtime" / "runtime.db"
    reader = StoredRuntimeReader(db, client_id="client-a")
    await reader._ensure_schema()
    await reader._write_history_items(
        "client-a:default", "overwrite-me",
        [HistoryItem(item_id="old-h", thread_id="overwrite-me", turn_id="old",
                     role="user", content="stale", payload={}, created_at=time.time())],
    )
    document = {
        "version": 1,
        "thread": {"thread_id": "overwrite-me", "title": "OW", "status": "active",
                    "created_at": 1.0, "updated_at": 1.0},
        "ledgerItems": [
            {"itemType": "message", "turnId": "turn-1", "seq": 1, "role": "user",
             "content": "fresh", "payload": {}, "createdAt": 1.0},
        ],
    }
    # First import (no overwrite) should fail because thread already exists
    # ...but our setup seeded history items without a thread row, so let's create one
    import aiosqlite
    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute(
            """INSERT INTO runtime_threads (thread_id, session_id, title, status, created_at, updated_at, metadata_json)
               VALUES ('overwrite-me','client-a:default','OW','active',1.0,1.0,'{}')""")
        await conn.commit()

    # Now import with overwrite
    resp = await server.dispatch(
        "1", "thread/import",
        {"document": document, "overwrite": True, "includeTurns": True},
        "client-a", None,
    )
    assert resp["result"]["thread"]["id"] == "overwrite-me"
    # Stale history item should be gone; only fresh one should remain
    msgs = await reader.load_provider_messages(
        await reader.resolve_thread("overwrite-me"),
    )
    assert len(msgs) == 1
    assert msgs[0]["content"] == "fresh"
