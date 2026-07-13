import json
from pathlib import Path

from miqi.session.manager import SessionManager


def _conversation_path(tmp_path: Path, key: str) -> Path:
    return tmp_path / "sessions" / key / "conversation.jsonl"


def _read_metadata(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.loads(f.readline())


def test_append_save_rewrites_metadata_updated_at(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("chat:1")

    session.add_message("user", "first", timestamp="2026-01-01T00:00:00")
    manager.save(session)

    path = _conversation_path(tmp_path, "chat_1")
    assert _read_metadata(path)["updated_at"] == "2026-01-01T00:00:00"

    session.add_message("assistant", "second", timestamp="2026-01-01T00:05:00")
    manager.save(session)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["updated_at"] == "2026-01-01T00:05:00"
    assert manager.list_sessions()[0]["updated_at"] == "2026-01-01T00:05:00"


def test_compact_preserves_latest_message_timestamp_as_updated_at(tmp_path):
    manager = SessionManager(
        tmp_path,
        compact_threshold_messages=999,
        compact_keep_messages=2,
    )
    session = manager.get_or_create("chat:2")
    session.add_message("user", "first", timestamp="2026-01-01T00:00:00")
    session.add_message("assistant", "second", timestamp="2026-01-01T00:03:00")
    session.add_message("user", "third", timestamp="2026-01-01T00:07:00")
    manager.save(session)

    assert manager.compact("chat:2") is True

    path = _conversation_path(tmp_path, "chat_2")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["updated_at"] == "2026-01-01T00:07:00"
