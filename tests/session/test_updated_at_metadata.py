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


def test_invalid_message_timestamp_is_canonicalized_before_save(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("chat:invalid")

    session.add_message("user", "first", timestamp="2026-01-01T00:00:00")
    session.add_message("assistant", "second", timestamp="not-a-date")
    manager.save(session)

    path = _conversation_path(tmp_path, "chat_invalid")
    lines = path.read_text(encoding="utf-8").splitlines()
    second_message = json.loads(lines[2])
    metadata = json.loads(lines[0])

    assert second_message["timestamp"] != "not-a-date"
    assert second_message["timestamp"] == metadata["updated_at"]


def test_mixed_timezone_message_timestamps_are_comparable(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("chat:tz")

    session.add_message("user", "aware", timestamp="2026-01-01T00:05:00+00:00")
    session.add_message("assistant", "naive", timestamp="2026-01-01T00:01:00")
    manager.save(session)

    path = _conversation_path(tmp_path, "chat_tz")
    metadata = _read_metadata(path)

    assert session.messages[0]["timestamp"] == "2026-01-01T00:05:00+00:00"
    assert metadata["updated_at"] == "2026-01-01T00:05:00"
    assert manager.list_sessions()[0]["updated_at"] == "2026-01-01T00:05:00"


def test_session_lock_is_reused_for_same_key(tmp_path):
    manager = SessionManager(tmp_path)

    assert manager._get_session_lock("chat:locked") is manager._get_session_lock(
        "chat:locked",
    )
