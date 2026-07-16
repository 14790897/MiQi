"""Tests for feedback handlers."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from miqi.runtime.app_server import AppServerError, ClientSessionRegistry


@pytest.fixture
def _bridge_state_isolated():
    """Save original bridge_module._state, then restore after the test.

    Other test files rely on ``_state`` being initialized to the real
    ``BridgeState()`` instance that ``miqi.bridge.server`` sets at
    module-import time.  Setting ``_state = None`` here would break them
    when tests are run together.  Use this fixture to safely mutate
    ``_state`` during a feedback test and restore it on teardown.
    """
    import miqi.bridge.server as bridge_module
    original = getattr(bridge_module, "_state", None)
    yield bridge_module
    bridge_module._state = original


def _make_workspace() -> Path:
    """Create a fresh temp workspace with memory/ and logs/ subdirs."""
    tmpdir = tempfile.mkdtemp(prefix="miqi-test-feedback-")
    workspace = Path(tmpdir)
    (workspace / "memory").mkdir(parents=True, exist_ok=True)
    (workspace / "logs").mkdir(parents=True, exist_ok=True)
    (workspace / "logs" / "test.log").write_text("[INFO] test log line\n")
    return workspace


def _make_mock_state(
    workspace: Path,
    *,
    enabled: bool = True,
    bitable_app_token: str = "test_app_token",
    bitable_table_id: str = "tbl_test",
    app_id: str = "cli_test",
    app_secret: str = "test_secret",
) -> MagicMock:
    """Build a mock BridgeState with feedback config pointing at ``workspace``."""
    from miqi.config.schema import Config

    state = MagicMock()
    cfg = Config()
    cfg.agents.defaults.workspace = str(workspace)
    cfg.channels.feedback.enabled = enabled
    cfg.channels.feedback.bitable_app_token = bitable_app_token
    cfg.channels.feedback.bitable_table_id = bitable_table_id
    cfg.channels.feishu.app_id = app_id
    cfg.channels.feishu.app_secret = app_secret
    state.load_config.return_value = cfg
    return state


# ── feedback:list tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feedback_list_returns_entries():
    """feedback:list returns entries array (empty when no feedback submitted)."""
    from miqi.runtime.feedback_handlers import feedback_list_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace)
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace):
        result = await feedback_list_handler("req-1", {}, "client-1", None, registry)
        assert "entries" in result["result"]
        assert isinstance(result["result"]["entries"], list)


@pytest.mark.asyncio
async def test_feedback_list_respects_limit():
    from miqi.runtime.feedback_handlers import feedback_list_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace)
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace):
        result = await feedback_list_handler("req-1", {"limit": 5}, "client-1", None, registry)
        assert "entries" in result["result"]


@pytest.mark.asyncio
async def test_feedback_list_handles_null_limit():
    """params.get('limit', 50) crashes on explicit null; use params.get('limit') or 50."""
    from miqi.runtime.feedback_handlers import feedback_list_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace)
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace):
        # Should not raise TypeError
        result = await feedback_list_handler("req-1", {"limit": None}, "client-1", None, registry)
        assert "entries" in result["result"]


# ── feedback:submit validation tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_feedback_submit_requires_title(_bridge_state_isolated):
    from miqi.runtime.feedback_handlers import feedback_submit_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace)
    _bridge_state_isolated._state = state
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace):
        with pytest.raises(AppServerError, match="标题不能为空"):
            await feedback_submit_handler(
                "req-1", {"content": "some content"}, "client-1", None, registry,
            )


@pytest.mark.asyncio
async def test_feedback_submit_requires_content(_bridge_state_isolated):
    from miqi.runtime.feedback_handlers import feedback_submit_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace)
    _bridge_state_isolated._state = state
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace):
        with pytest.raises(AppServerError, match="内容不能为空"):
            await feedback_submit_handler(
                "req-1", {"title": "some title"}, "client-1", None, registry,
            )


@pytest.mark.asyncio
async def test_feedback_submit_rejects_when_disabled(_bridge_state_isolated):
    from miqi.runtime.feedback_handlers import feedback_submit_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace, enabled=False)
    _bridge_state_isolated._state = state
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace):
        with pytest.raises(AppServerError, match="未启用"):
            await feedback_submit_handler(
                "req-1", {"title": "test", "content": "test content"}, "client-1", None, registry,
            )


@pytest.mark.asyncio
async def test_feedback_submit_rejects_when_no_feishu_credentials(_bridge_state_isolated):
    from miqi.runtime.feedback_handlers import feedback_submit_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace, app_id="", app_secret="")
    _bridge_state_isolated._state = state
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace):
        with pytest.raises(AppServerError, match="未配置"):
            await feedback_submit_handler(
                "req-1", {"title": "test", "content": "test content"}, "client-1", None, registry,
            )


@pytest.mark.asyncio
async def test_feedback_submit_rejects_when_no_bitable_config(_bridge_state_isolated):
    from miqi.runtime.feedback_handlers import feedback_submit_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace, bitable_app_token="", bitable_table_id="")
    _bridge_state_isolated._state = state
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace):
        with pytest.raises(AppServerError, match="未配置"):
            await feedback_submit_handler(
                "req-1", {"title": "test", "content": "test content"}, "client-1", None, registry,
            )


@pytest.mark.asyncio
async def test_feedback_submit_invalid_category_falls_back_to_other(_bridge_state_isolated):
    """Unknown category values should fall back to 'other' instead of being passed through."""
    from miqi.runtime.feedback_handlers import feedback_submit_handler

    workspace = _make_workspace()
    state = _make_mock_state(workspace)
    _bridge_state_isolated._state = state
    registry = ClientSessionRegistry()
    registry.bridge_context["state"] = state

    with patch("miqi.runtime.feedback_handlers._get_workspace_path", return_value=workspace), \
         patch("miqi.runtime.feedback_handlers._get_tenant_access_token", return_value="mock_token"), \
         patch("miqi.runtime.feedback_handlers._add_bitable_record", return_value="rec_123") as mock_add:
        await feedback_submit_handler(
            "req-1",
            {"title": "test", "content": "test content", "category": "INVALID"},
            "client-1", None, registry,
        )
        fields = mock_add.call_args[0][3]
        assert fields["类别"] == "other"


# ── Helper function tests ────────────────────────────────────────────────────


def test_collect_all_logs_empty_dir(tmp_path):
    from miqi.runtime.feedback_handlers import _collect_all_logs
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    result = _collect_all_logs(log_dir)
    assert "无日志文件" in result


def test_collect_all_logs_reads_log_files(tmp_path):
    from miqi.runtime.feedback_handlers import _collect_all_logs
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "test.log").write_text("[INFO] line1\n[WARN] line2\n")
    result = _collect_all_logs(log_dir)
    assert "test.log" in result
    assert "line1" in result


def test_collect_all_logs_nonexistent_dir():
    from miqi.runtime.feedback_handlers import _collect_all_logs
    result = _collect_all_logs(Path("/nonexistent/path/12345"))
    assert "日志目录不存在" in result


def test_collect_all_logs_caps_combined_payload_at_100k_bytes(tmp_path):
    """Combined log payload must be capped at 100k UTF-8 bytes for Bitable text-field.

    Feishu Bitable's text-field limit is 100k bytes (not chars).  Chinese
    characters are 3+ bytes each in UTF-8, so a naive 100k-char cap can
    still exceed the byte limit.  Verify the cap is enforced in bytes.
    """
    from miqi.runtime.feedback_handlers import _collect_all_logs
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    # 200k ASCII chars -> ~200k bytes UTF-8 (1 byte each)
    (log_dir / "big.log").write_text("a" * 200_000, encoding="utf-8")
    result = _collect_all_logs(log_dir)
    # The cap truncates iteratively until the result fits within 100k bytes
    # plus a small marker overhead
    assert len(result.encode("utf-8")) <= 100_300


def test_collect_all_logs_byte_cap_handles_multibyte_chars(tmp_path):
    """Multi-byte chars (CJK, 3 bytes/char in UTF-8) must be byte-capped, not char-capped."""
    from miqi.runtime.feedback_handlers import _collect_all_logs
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    # 50k CJK chars = ~150k bytes UTF-8, exceeds 100k byte cap
    (log_dir / "cjk.log").write_text("中" * 50_000, encoding="utf-8")
    result = _collect_all_logs(log_dir)
    assert len(result.encode("utf-8")) <= 100_300


def test_collect_system_info():
    from miqi.runtime.feedback_handlers import _collect_system_info
    info = _collect_system_info()
    assert "os" in info
    assert "python_version" in info
    assert "machine" in info


def test_read_local_backups_empty(tmp_path):
    import miqi.runtime.feedback_handlers as handlers
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    feedback_file = memory_dir / "FEEDBACK.jsonl"
    with patch.object(handlers, '_get_feedback_file', return_value=feedback_file):
        result = handlers._read_local_backups()
        assert result == []


def test_read_local_backups_returns_newest_first(tmp_path):
    import miqi.runtime.feedback_handlers as handlers
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    feedback_file = memory_dir / "FEEDBACK.jsonl"
    entries = [
        {"id": "1", "title": "old", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "2", "title": "new", "created_at": "2026-07-01T00:00:00Z"},
    ]
    feedback_file.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n"
    )
    with patch.object(handlers, '_get_feedback_file', return_value=feedback_file):
        result = handlers._read_local_backups()
        assert len(result) == 2
        assert result[0]["id"] == "2"
        assert result[1]["id"] == "1"


def test_read_local_backups_skips_blank_lines(tmp_path):
    import miqi.runtime.feedback_handlers as handlers
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    feedback_file = memory_dir / "FEEDBACK.jsonl"
    feedback_file.write_text(
        '{"id": "1", "title": "test", "created_at": "2026-01-01T00:00:00Z"}\n\n\n'
    )
    with patch.object(handlers, '_get_feedback_file', return_value=feedback_file):
        result = handlers._read_local_backups()
        assert len(result) == 1


def test_read_local_backups_skips_invalid_json(tmp_path):
    import miqi.runtime.feedback_handlers as handlers
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    feedback_file = memory_dir / "FEEDBACK.jsonl"
    feedback_file.write_text(
        '{"id": "1", "title": "good", "created_at": "2026-01-01T00:00:00Z"}\n'
        'not valid json\n'
        '{"id": "2", "title": "also good", "created_at": "2026-01-02T00:00:00Z"}\n'
    )
    with patch.object(handlers, '_get_feedback_file', return_value=feedback_file):
        result = handlers._read_local_backups()
        assert len(result) == 2


def test_save_local_backup_creates_file(tmp_path):
    import miqi.runtime.feedback_handlers as handlers
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    feedback_file = memory_dir / "FEEDBACK.jsonl"
    with patch.object(handlers, '_get_feedback_file', return_value=feedback_file):
        with patch.object(handlers, '_ensure_memory_dir'):
            handlers._save_local_backup({"id": "1", "title": "test"})
    lines = feedback_file.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == "1"


def test_save_local_backup_appends_to_existing(tmp_path):
    import miqi.runtime.feedback_handlers as handlers
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    feedback_file = memory_dir / "FEEDBACK.jsonl"
    feedback_file.write_text('{"id": "1", "title": "first"}\n')
    with patch.object(handlers, '_get_feedback_file', return_value=feedback_file):
        with patch.object(handlers, '_ensure_memory_dir'):
            handlers._save_local_backup({"id": "2", "title": "second"})
    lines = feedback_file.read_text().strip().splitlines()
    assert len(lines) == 2


def test_backward_compat_aliases_exist(tmp_path):
    """Verify _append_feedback and _read_local_feedbacks aliases are callable."""
    import miqi.runtime.feedback_handlers as handlers
    from miqi.runtime.feedback_handlers import _append_feedback, _read_local_feedbacks

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    feedback_file = memory_dir / "FEEDBACK.jsonl"
    with patch.object(handlers, '_get_feedback_file', return_value=feedback_file):
        with patch.object(handlers, '_ensure_memory_dir'):
            _append_feedback({"id": "a", "title": "via alias"})
        result = _read_local_feedbacks()
        assert len(result) == 1
        assert result[0]["id"] == "a"