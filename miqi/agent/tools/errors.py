"""Tool-layer permission errors with user-facing Chinese messages.

The English technical detail stays in ``str(exc)`` — it is logged
server-side and matched by existing tests — while ``user_message`` carries
the Chinese text shown to the user (issue #691).
"""


class ToolPermissionError(PermissionError):
    """PermissionError carrying a user-facing Chinese message.

    ``str(exc)`` keeps the English technical detail (server logs / existing
    ``pytest.raises(PermissionError, match=...)`` assertions depend on it);
    ``user_message`` is what the UI shows and what the model is fed.
    """

    def __init__(self, user_message: str, tech_message: str):
        super().__init__(tech_message)
        self.user_message = user_message


def outside_allowed_dir_error(path, effective_dir=None) -> ToolPermissionError:
    """Uniform "path outside allowed directory" error used by the documents
    tools (docx / xlsx / pptx / pdf)."""
    suffix = f" '{effective_dir}'" if effective_dir is not None else ""
    return ToolPermissionError(
        user_message=(
            "文件访问被拒绝：该路径不在允许访问的目录范围内"
            f"（{path}）。如需允许访问，请在设置中为该目录添加访问权限"
            "（tools.extra_roots）。"
        ),
        tech_message=f"Path '{path}' resolves outside allowed directory{suffix}",
    )


def permission_error_result(e: PermissionError) -> str:
    """Stringify a caught PermissionError for a tool result.

    Prefer the Chinese ``user_message`` when present; fall back to the
    historical English form otherwise (e.g. OS-level file-lock errors that
    are not ToolPermissionError).
    """
    user_msg = getattr(e, "user_message", None)
    return f"错误：{user_msg}" if user_msg else f"Error: Permission denied: {e}"
