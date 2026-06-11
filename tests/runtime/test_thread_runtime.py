"""Tests for ThreadRuntime — persistent thread lifecycle."""

import pytest

from miqi.runtime.thread_runtime import ThreadRuntime


@pytest.mark.asyncio
async def test_thread_runtime_create_rename_archive_delete(tmp_path):
    runtime = ThreadRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await runtime.initialize()

    thread = await runtime.create_thread(title="First")
    assert thread.thread_id
    assert thread.title == "First"
    assert thread.status == "active"

    renamed = await runtime.rename_thread(thread.thread_id, "Renamed")
    assert renamed.title == "Renamed"

    archived = await runtime.archive_thread(thread.thread_id)
    assert archived.status == "archived"

    await runtime.delete_thread(thread.thread_id)
    assert await runtime.get_thread(thread.thread_id) is None


@pytest.mark.asyncio
async def test_thread_runtime_fork_records_parent(tmp_path):
    runtime = ThreadRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await runtime.initialize()

    parent = await runtime.create_thread(title="Parent")
    child = await runtime.fork_thread(parent.thread_id, title="Child")

    assert child.parent_thread_id == parent.thread_id
    assert child.status == "active"


@pytest.mark.asyncio
async def test_thread_runtime_list_threads(tmp_path):
    runtime = ThreadRuntime(tmp_path / "runtime.db", session_id="sess-2")
    await runtime.initialize()

    await runtime.create_thread(title="Alpha")
    await runtime.create_thread(title="Beta")
    archived = await runtime.create_thread(title="Gamma")
    await runtime.archive_thread(archived.thread_id)

    active = await runtime.list_threads()
    assert len(active) == 2
    titles = {t.title for t in active}
    assert titles == {"Alpha", "Beta"}

    all_threads = await runtime.list_threads(include_archived=True)
    assert len(all_threads) == 3
