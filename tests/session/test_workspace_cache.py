"""SessionManager.save() workspace-cache behavior (CodeRabbit #682 review):

_read_workspace reads the WHOLE session file, so after a successful persist the
workspace check must NOT re-read the disk on every subsequent save.
"""
from miqi.session.manager import Session, SessionManager


def _mk_manager(tmp_path):
    return SessionManager(workspace=tmp_path)


def _mk_session(key, workspace):
    from datetime import datetime

    return Session(
        key=key,
        messages=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={"workspace": workspace},
    )


def test_save_workspace_change_triggers_rewrite_once_then_caches(tmp_path, monkeypatch):
    m = _mk_manager(tmp_path)
    s = _mk_session("s1", "/ws/a")
    m.save(s)
    # persisted → cache set, on-disk metadata matches
    assert getattr(s, "_persisted_workspace", None) == "/ws/a"

    reads = {"n": 0}
    real = m._read_workspace

    def counting(key):
        reads["n"] += 1
        return real(key)

    monkeypatch.setattr(m, "_read_workspace", counting)

    # Same-session save with no new messages: no disk read (cache hit)
    m.save(s)
    assert reads["n"] == 0

    # Workspace change still forces the rewrite on the next save
    s.metadata["workspace"] = "/ws/b"
    m.save(s)
    assert reads["n"] == 0  # cache hit — still no disk read
    assert getattr(s, "_persisted_workspace", None) == "/ws/b"
    # disk now carries the new workspace
    assert m._read_workspace("s1") == "/ws/b"


def test_save_workspace_cache_resets_when_disk_changed_externally(tmp_path):
    """A fresh Session object (new process / reload) re-reads the disk."""
    m = _mk_manager(tmp_path)
    s = _mk_session("s2", "/ws/a")
    m.save(s)
    # simulate an external writer changing the workspace on disk
    s2 = _mk_session("s2", "/ws/c")
    m.save(s2)
    fresh = m._load("s2")
    assert fresh is not None and fresh.metadata.get("workspace") == "/ws/c"
