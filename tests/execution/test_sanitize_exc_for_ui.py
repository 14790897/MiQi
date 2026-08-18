"""Tests for orchestrator._sanitize_exc_for_ui (issue #691).

The function decides what error text reaches the frontend: tool-layer
PermissionErrors carry a Chinese ``user_message`` which must be preferred
over the English tech summary; all other exceptions keep the historical
sanitized-English behavior.
"""

import pytest

from miqi.agent.tools.errors import ToolPermissionError
from miqi.execution.orchestrator import _sanitize_exc_for_ui


def test_tool_permission_error_returns_chinese_user_message():
    err = ToolPermissionError(
        user_message="文件访问被拒绝：该路径不在允许访问的目录范围内（C:/x）。如需允许访问，请在设置中为该目录添加访问权限（tools.extra_roots）。",
        tech_message="Path 'C:/x' resolves outside all legal roots. tools.extra_roots",
    )
    out = _sanitize_exc_for_ui(err)
    assert out == err.user_message
    assert "文件访问被拒绝" in out
    # The English tech detail must NOT leak to the UI.
    assert "legal roots" not in out


def test_plain_permission_error_keeps_english_sanitized():
    out = _sanitize_exc_for_ui(
        PermissionError("Path C:/Users/foo/secret.txt resolves outside all legal roots")
    )
    assert out.startswith("PermissionError:")
    assert "legal roots" in out


def test_path_and_url_redaction_still_applies_to_plain_errors():
    out = _sanitize_exc_for_ui(
        PermissionError("Failed at /Users/foo/secret/read with https://api.example.com/v1")
    )
    # The path regex eats the URL after `https:` (existing behavior), so both
    # the local path and the remote host are redacted into [path].
    assert "[path]" in out
    assert "/Users/foo/secret/read" not in out
    assert "api.example.com" not in out


def test_exception_without_message_uses_type_name():
    out = _sanitize_exc_for_ui(ValueError())
    assert out == "ValueError"
