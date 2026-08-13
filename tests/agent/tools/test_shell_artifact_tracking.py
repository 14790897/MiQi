"""Phase 59 subprocess artifact tracking (#607): exec-created files become
write tracked assets.

Covers the snapshot/diff/persist helpers on ExecTool; the end-to-end path
(exec → tracked_files.json → Task Assets panel) is covered by the MOF
journey e2e.
"""

import os
from pathlib import Path

import pytest

from miqi.agent.tools.shell import ExecTool


@pytest.fixture
def exec_tool() -> ExecTool:
    tool = ExecTool()
    tool.working_dir = None
    return tool


@pytest.fixture
def fake_workspace(tmp_path, monkeypatch) -> Path:
    """Point _get_workspace_path() at a temp dir and seed it."""
    root = tmp_path / "workspace"
    root.mkdir()

    def _fake_workspace_path():
        return str(root)

    monkeypatch.setattr(
        "miqi.runtime.file_handlers._get_workspace_path",
        _fake_workspace_path,
    )
    return root


def test_snapshot_records_files(exec_tool, fake_workspace):
    (fake_workspace / "a.txt").write_text("hello")
    (fake_workspace / "sub").mkdir()
    (fake_workspace / "sub" / "b.csv").write_text("x,y")

    snap = exec_tool._snapshot_workspace()

    assert len(snap) == 2
    a_key = str(fake_workspace / "a.txt")
    assert snap[a_key][1] == 5  # size of "hello"
    assert isinstance(snap[a_key][0], int)  # mtime_ns


def test_snapshot_excludes_noise_dirs(exec_tool, fake_workspace):
    (fake_workspace / "report.md").write_text("deliverable")
    for noise in (".git", "node_modules", "sessions", ".miqi-runtime", "logs", "__pycache__"):
        (fake_workspace / noise).mkdir()
        (fake_workspace / noise / "x.txt").write_text("noise")

    snap = exec_tool._snapshot_workspace()

    keys = set(snap.keys())
    assert str(fake_workspace / "report.md") in keys
    assert not any(n in k for k in keys for n in ("node_modules", ".git", "sessions"))
    assert len(snap) == 1


def test_snapshot_bails_on_oversized_workspace(exec_tool, fake_workspace, monkeypatch):
    monkeypatch.setattr(exec_tool, "_WORKSPACE_SNAPSHOT_MAX_FILES", 3)
    for i in range(5):
        (fake_workspace / f"f{i}.txt").write_text("x")

    assert exec_tool._snapshot_workspace() is None


def test_snapshot_missing_workspace_returns_none(exec_tool, monkeypatch):
    monkeypatch.setattr(
        "miqi.runtime.file_handlers._get_workspace_path",
        lambda: str(Path("C:/nonexistent_workspace_xyz")),
    )
    assert exec_tool._snapshot_workspace() is None


@pytest.mark.asyncio
async def test_track_persists_new_files_as_write(exec_tool, fake_workspace, monkeypatch):
    # seed an existing file so the before-snapshot is non-empty
    (fake_workspace / "data.csv").write_text("col1,col2")
    before = exec_tool._snapshot_workspace()
    # subprocess creates a deliverable + modifies the existing file
    (fake_workspace / "output").mkdir()
    (fake_workspace / "output" / "report.md").write_text("final report")
    (fake_workspace / "data.csv").write_text("col1,col2,col3")

    persisted: list[tuple] = []

    def _fake_persist(workspace, file_path, op="write", session_key=None):
        persisted.append((str(workspace), str(file_path), op, session_key))

    monkeypatch.setattr(
        "miqi.agent.tools.filesystem._persist_tracked_file", _fake_persist
    )

    await exec_tool._track_workspace_changes(before, "desktop:test")

    paths = {p[1] for p in persisted}
    assert str(fake_workspace / "output" / "report.md") in paths
    assert str(fake_workspace / "data.csv") in paths
    assert all(p[2] == "write" for p in persisted)
    assert all(p[3] == "desktop:test" for p in persisted)


@pytest.mark.asyncio
async def test_track_skips_unchanged_files(exec_tool, fake_workspace, monkeypatch):
    (fake_workspace / "existing.txt").write_text("v1")
    before = exec_tool._snapshot_workspace()

    persisted: list[tuple] = []

    def _fake_persist(workspace, file_path, op="write", session_key=None):
        persisted.append((str(workspace), str(file_path), op, session_key))

    monkeypatch.setattr(
        "miqi.agent.tools.filesystem._persist_tracked_file", _fake_persist
    )

    await exec_tool._track_workspace_changes(before, "desktop:test")

    assert persisted == []


@pytest.mark.asyncio
async def test_track_noop_without_before(exec_tool, fake_workspace, monkeypatch):
    called = False

    def _fake_persist(workspace, file_path, op="write", session_key=None):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "miqi.agent.tools.filesystem._persist_tracked_file", _fake_persist
    )

    await exec_tool._track_workspace_changes(None, "desktop:test")
    assert not called


@pytest.mark.asyncio
async def test_track_empty_before_diffs_everything(exec_tool, fake_workspace, monkeypatch):
    """An empty before-snapshot (workspace had no files) must still diff —
    every file after the exec is then new (regression: `not before` used to
    short-circuit and skip tracking entirely)."""
    before = exec_tool._snapshot_workspace()  # empty workspace → {}
    assert before == {}
    (fake_workspace / "output").mkdir()
    (fake_workspace / "output" / "deliverable.md").write_text("done")

    persisted: list[tuple] = []

    def _fake_persist(workspace, file_path, op="write", session_key=None):
        persisted.append((str(workspace), str(file_path), op, session_key))

    monkeypatch.setattr(
        "miqi.agent.tools.filesystem._persist_tracked_file", _fake_persist
    )

    await exec_tool._track_workspace_changes(before, "desktop:test")

    assert any("deliverable.md" in p[1] for p in persisted)


@pytest.mark.asyncio
async def test_track_ignores_tracked_files_json_self_write(
    exec_tool, fake_workspace, monkeypatch
):
    """The app's own state files (tracked_files.json under sessions/) must
    never be tracked — that would self-reference the panel."""
    (fake_workspace / "existing.txt").write_text("v1")
    before = exec_tool._snapshot_workspace()
    # simulate the app writing its own session state during exec
    sess_dir = fake_workspace / "sessions" / "desktop_x"
    sess_dir.mkdir(parents=True)
    (sess_dir / "tracked_files.json").write_text('{"version": 1}')

    persisted: list[tuple] = []

    def _fake_persist(workspace, file_path, op="write", session_key=None):
        persisted.append((str(workspace), str(file_path), op, session_key))

    monkeypatch.setattr(
        "miqi.agent.tools.filesystem._persist_tracked_file", _fake_persist
    )

    await exec_tool._track_workspace_changes(before, "desktop:test")
    assert persisted == []
