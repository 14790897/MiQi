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
