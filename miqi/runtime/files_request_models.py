"""Typed request params for files.* App Server methods (Phase 30 files handlers)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Params(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class FilesCheckItemModel(_Params):
    """Single asset-panel path check item (issue #790)."""

    path: str
    truncated: bool = False
    op: str | None = None


class FilesCheckManyParams(_Params):
    """files.check_many — 资产面板路径可达性批量校验（#790）。

    session_key 可选：提供时按会话作用域解析（#731 会话隔离），
    否则按 workspace 作用域解析。
    """

    items: list[FilesCheckItemModel] = Field(default_factory=list)
    session_key: str | None = None
