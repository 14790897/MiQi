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
    await runtime.close()


@pytest.mark.asyncio
async def test_thread_runtime_fork_records_parent(tmp_path):
    runtime = ThreadRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await runtime.initialize()

    parent = await runtime.create_thread(title="Parent")
    child = await runtime.fork_thread(parent.thread_id, title="Child")

    assert child.parent_thread_id == parent.thread_id
    assert child.status == "active"
    await runtime.close()


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
    await runtime.close()


@pytest.mark.asyncio
async def test_thread_runtime_cross_session_same_thread_id(tmp_path):
    """Two sessions sharing a DB can each own a thread with the same thread_id."""
    db_path = tmp_path / "shared.db"

    rt_a = ThreadRuntime(db_path, session_id="sess-A")
    await rt_a.initialize()
    rt_b = ThreadRuntime(db_path, session_id="sess-B")
    await rt_b.initialize()

    # Both sessions create a thread with the same thread_id
    ta = await rt_a.create_thread(thread_id="same-thread", title="Alpha thread")
    tb = await rt_b.create_thread(thread_id="same-thread", title="Beta thread")

    assert ta.thread_id == "same-thread"
    assert ta.session_id == "sess-A"
    assert tb.thread_id == "same-thread"
    assert tb.session_id == "sess-B"

    # Each session sees only its own thread
    assert (await rt_a.get_thread("same-thread")).title == "Alpha thread"  # type: ignore[union-attr]
    assert (await rt_b.get_thread("same-thread")).title == "Beta thread"  # type: ignore[union-attr]

    # Listing only returns own session's threads
    a_list = await rt_a.list_threads()
    b_list = await rt_b.list_threads()
    assert len(a_list) == 1 and a_list[0].title == "Alpha thread"
    assert len(b_list) == 1 and b_list[0].title == "Beta thread"

    # Deleting in one session doesn't affect the other
    await rt_a.delete_thread("same-thread")
    assert await rt_a.get_thread("same-thread") is None
    assert await rt_b.get_thread("same-thread") is not None
    await rt_a.close()
    await rt_b.close()
