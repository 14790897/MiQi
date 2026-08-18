"""Test session history consolidation and compaction through the real
Session / SessionManager APIs."""

from pathlib import Path

import pytest

from miqi.session.manager import Session, SessionManager


def create_session_with_messages(key: str, count: int, role: str = "user") -> Session:
    """Create a session and add the specified number of messages.

    Args:
        key: Session identifier
        count: Number of messages to add
        role: Message role (default: "user")

    Returns:
        Session with the specified messages
    """
    session = Session(key=key)
    for i in range(count):
        session.add_message(role, f"msg{i}")
    return session


class TestSessionLastConsolidated:
    """Test last_consolidated tracking to avoid duplicate processing."""

    def test_initial_last_consolidated_zero(self) -> None:
        """Test that new session starts with last_consolidated=0."""
        session = Session(key="test:initial")
        assert session.last_consolidated == 0

    def test_last_consolidated_persistence(self, tmp_path) -> None:
        """Test that last_consolidated persists across save/load."""
        manager = SessionManager(Path(tmp_path))
        session1 = create_session_with_messages("test:persist", 20)
        session1.last_consolidated = 15
        manager.save(session1)

        session2 = manager.get_or_create("test:persist")
        assert session2.last_consolidated == 15
        assert len(session2.messages) == 20

    def test_clear_resets_last_consolidated(self) -> None:
        """Test that clear() resets last_consolidated to 0."""
        session = create_session_with_messages("test:clear", 10)
        session.last_consolidated = 5

        session.clear()
        assert len(session.messages) == 0
        assert session.last_consolidated == 0


class TestSessionImmutableHistory:
    """Test Session message immutability for cache efficiency."""

    def test_initial_state(self) -> None:
        """Test that new session has empty messages list."""
        session = Session(key="test:initial")
        assert len(session.messages) == 0

    def test_add_messages_appends_only(self) -> None:
        """Test that adding messages only appends, never modifies."""
        session = Session(key="test:preserve")
        session.add_message("user", "msg1")
        session.add_message("assistant", "resp1")
        session.add_message("user", "msg2")
        assert len(session.messages) == 3
        assert session.messages[0]["content"] == "msg1"

    def test_get_history_returns_most_recent(self) -> None:
        """Test get_history returns the most recent messages."""
        session = Session(key="test:history")
        for i in range(10):
            session.add_message("user", f"msg{i}")
            session.add_message("assistant", f"resp{i}")

        history = session.get_history(max_messages=6)
        assert len(history) == 6
        assert history[0]["content"] == "msg7"
        assert history[-1]["content"] == "resp9"

    def test_get_history_with_all_messages(self) -> None:
        """Test get_history with max_messages larger than actual."""
        session = create_session_with_messages("test:all", 5)
        history = session.get_history(max_messages=100)
        assert len(history) == 5
        assert history[0]["content"] == "msg0"

    def test_get_history_stable_for_same_session(self) -> None:
        """Test that get_history returns same content for same max_messages."""
        session = create_session_with_messages("test:stable", 20)
        history1 = session.get_history(max_messages=10)
        history2 = session.get_history(max_messages=10)
        assert history1 == history2

    def test_messages_list_never_modified(self) -> None:
        """Test that messages list is never modified after creation."""
        session = create_session_with_messages("test:immutable", 5)
        original_len = len(session.messages)

        session.get_history(max_messages=2)
        assert len(session.messages) == original_len

        for _ in range(10):
            session.get_history(max_messages=3)
        assert len(session.messages) == original_len


class TestSessionPersistence:
    """Test Session persistence and reload."""

    @pytest.fixture
    def temp_manager(self, tmp_path):
        return SessionManager(Path(tmp_path))

    def test_persistence_roundtrip(self, temp_manager):
        """Test that messages persist across save/load."""
        session1 = create_session_with_messages("test:persistence", 20)
        temp_manager.save(session1)

        session2 = temp_manager.get_or_create("test:persistence")
        assert len(session2.messages) == 20
        assert session2.messages[0]["content"] == "msg0"
        assert session2.messages[-1]["content"] == "msg19"

    def test_get_history_after_reload(self, temp_manager):
        """Test that get_history works correctly after reload."""
        session1 = create_session_with_messages("test:reload", 30)
        temp_manager.save(session1)

        session2 = temp_manager.get_or_create("test:reload")
        history = session2.get_history(max_messages=10)
        assert len(history) == 10
        assert history[0]["content"] == "msg20"
        assert history[-1]["content"] == "msg29"

    def test_clear_resets_session(self, temp_manager):
        """Test that clear() properly resets session."""
        session = create_session_with_messages("test:clear", 10)
        assert len(session.messages) == 10

        session.clear()
        assert len(session.messages) == 0


class TestGetHistoryConsolidation:
    """get_history must respect last_consolidated and LLM role constraints."""

    def test_history_ignores_consolidated_prefix(self) -> None:
        session = create_session_with_messages("test:offset", 20)
        session.last_consolidated = 15

        history = session.get_history(max_messages=100)
        assert len(history) == 5
        assert history[0]["content"] == "msg15"
        assert history[-1]["content"] == "msg19"

    def test_history_slices_recent_tail_within_unconsolidated(self) -> None:
        session = create_session_with_messages("test:tail", 60)
        session.last_consolidated = 10

        # Unconsolidated = msg10..msg59 (50 items) → last 25 = msg35..msg59
        history = session.get_history(max_messages=25)
        assert len(history) == 25
        assert history[0]["content"] == "msg35"
        assert history[-1]["content"] == "msg59"

    def test_history_drops_leading_non_user_messages(self) -> None:
        session = Session(key="test:orphan")
        session.add_message("assistant", "resp0")
        session.add_message("tool", "tool0")
        session.add_message("user", "msg0")
        session.add_message("assistant", "resp1")

        history = session.get_history(max_messages=100)
        assert [m["content"] for m in history] == ["msg0", "resp1"]

    def test_history_with_no_user_message_returns_empty(self) -> None:
        """A window with no user turn has nothing to align to — history is
        empty instead of orphaned assistant/tool rows."""
        session = Session(key="test:no-user")
        session.add_message("assistant", "resp0")
        session.add_message("tool", "tool0")

        history = session.get_history(max_messages=100)
        assert history == []

        # The unconsolidated cursor must not change the outcome
        session.add_message("user", "msg0")
        session.last_consolidated = 2
        history = session.get_history(max_messages=100)
        assert [m["content"] for m in history] == ["msg0"]

    def test_history_maps_subagent_role_to_assistant(self) -> None:
        session = Session(key="test:subagent")
        session.add_message("user", "msg0")
        session.add_message("subagent", "sub result", name="spawn")

        history = session.get_history(max_messages=100)
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "sub result"

    def test_history_returns_simplified_entries(self) -> None:
        session = Session(key="test:shape")
        session.add_message("user", "hi", tool_calls=[{"id": "c1"}])

        history = session.get_history(max_messages=100)
        assert set(history[0].keys()) == {"role", "content", "tool_calls"}


class TestSessionManagerCompact:
    """compact() truncates the file to compact_keep_messages and realigns
    last_consolidated; compaction only fires past the configured thresholds."""

    def _manager(self, tmp_path: Path, **kwargs) -> SessionManager:
        return SessionManager(
            Path(tmp_path),
            compact_keep_messages=25,
            legacy_sessions_dir=Path(tmp_path) / "legacy-sessions",
            **kwargs,
        )

    def test_compact_truncates_messages_and_realigns_cursor(self, tmp_path) -> None:
        manager = self._manager(tmp_path)
        session = create_session_with_messages("test:compact", 60)
        session.last_consolidated = 15
        manager.save(session)

        assert manager.compact("test:compact") is True

        # Reload through a NEW manager: get_or_create returns the cached
        # session without reading the file, so a fresh instance proves the
        # compacted state was persisted to disk.
        reloaded = SessionManager(
            Path(tmp_path),
            legacy_sessions_dir=Path(tmp_path) / "legacy-sessions",
        ).get_or_create("test:compact")
        assert len(reloaded.messages) == 25
        assert reloaded.messages[0]["content"] == "msg35"
        assert reloaded.messages[-1]["content"] == "msg59"
        # Cursor realigned: 15 - (60 - 25) = -20 → clamped to 0
        assert reloaded.last_consolidated == 0
        # History after compact covers exactly the kept window
        assert len(reloaded.get_history(max_messages=100)) == 25

    def test_compact_rewrites_file_on_disk(self, tmp_path) -> None:
        manager = self._manager(tmp_path)
        manager.save(create_session_with_messages("test:ondisk", 40))

        manager.compact("test:ondisk")

        path = manager._get_session_path("test:ondisk")
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 26  # metadata + 25 kept messages

    def test_compact_missing_session_returns_false(self, tmp_path) -> None:
        manager = self._manager(tmp_path)
        assert manager.compact("test:missing") is False

    def test_compact_if_needed_skips_below_threshold(self, tmp_path) -> None:
        manager = self._manager(tmp_path)
        manager.save(create_session_with_messages("test:below", 10))

        assert manager.compact_if_needed("test:below") is False
        assert len(manager.get_or_create("test:below").messages) == 10

    def test_save_triggers_compact_past_threshold(self, tmp_path) -> None:
        manager = SessionManager(
            Path(tmp_path),
            compact_threshold_messages=10,
            compact_keep_messages=5,
            legacy_sessions_dir=Path(tmp_path) / "legacy-sessions",
        )
        # save() calls compact_if_needed at the end — the session is
        # truncated on disk the moment it crosses the threshold.  Reload
        # through a NEW manager to prove the state persisted to disk.
        manager.save(create_session_with_messages("test:auto", 30))

        reloaded = SessionManager(
            Path(tmp_path),
            legacy_sessions_dir=Path(tmp_path) / "legacy-sessions",
        ).get_or_create("test:auto")
        assert len(reloaded.messages) == 5
        assert reloaded.messages[-1]["content"] == "msg29"


class TestSessionManagerArchive:
    """archive() marks the session archived on disk; list_sessions filters it."""

    def _manager(self, tmp_path: Path) -> SessionManager:
        return SessionManager(
            Path(tmp_path),
            legacy_sessions_dir=Path(tmp_path) / "legacy-sessions",
        )

    def test_archive_marks_and_filters_session(self, tmp_path) -> None:
        manager = self._manager(tmp_path)
        manager.save(create_session_with_messages("test:arch", 5))
        manager.save(create_session_with_messages("test:keep", 5))

        manager.archive("test:arch")

        keys = [s["key"] for s in manager.list_sessions()]
        assert "test:keep" in keys
        assert "test:arch" not in keys

        with_archived = [
            s["key"] for s in manager.list_sessions(include_archived=True)
        ]
        assert "test:arch" in with_archived

    def test_unarchive_restores_visibility(self, tmp_path) -> None:
        manager = self._manager(tmp_path)
        manager.save(create_session_with_messages("test:unarch", 5))

        manager.archive("test:unarch")
        assert not any(
            s["key"] == "test:unarch" for s in manager.list_sessions()
        )

        manager.unarchive("test:unarch")
        assert any(
            s["key"] == "test:unarch" for s in manager.list_sessions()
        )
