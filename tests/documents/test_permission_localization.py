"""Documents-tool PermissionError localization (issue #691).

The documents tools (docx/xlsx/pptx/pdf) swallow PermissionError and
return a string as the tool result; that string must be Chinese/actionable
when the error is a ToolPermissionError, and keep the English fallback
otherwise.
"""

import pytest

from miqi.agent.tools.errors import (
    outside_allowed_dir_error,
    permission_error_result,
)
from miqi.documents.docx_tool import _enforce_boundary


def test_enforce_boundary_raises_tool_permission_error(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    with pytest.raises(PermissionError) as exc_info:
        _enforce_boundary(outside, allowed, None)
    err = exc_info.value
    assert type(err).__name__ == "ToolPermissionError"
    assert "文件访问被拒绝" in err.user_message
    assert "tools.extra_roots" in err.user_message
    # str(exc) keeps the English tech detail for server logs.
    assert "outside allowed directory" in str(err)


def test_permission_error_result_prefers_chinese():
    err = outside_allowed_dir_error("C:/x/test.pdf", "C:/ws")
    out = permission_error_result(err)
    assert out.startswith("错误：")
    assert "文件访问被拒绝" in out
    assert "tools.extra_roots" in out


def test_permission_error_result_falls_back_to_english():
    out = permission_error_result(PermissionError("OS-level lock"))
    assert out == "Error: Permission denied: OS-level lock"
