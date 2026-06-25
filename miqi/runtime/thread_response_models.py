"""Typed result payloads for thread/* App Server methods."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Result(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ThreadResult(_Result):
    """Single thread view result."""

    thread: dict[str, Any]


class ThreadPageResult(_Result):
    """Paginated thread list result."""

    items: list[dict[str, Any]]
    next_cursor: str | None = Field(default=None, validation_alias="nextCursor")


class ThreadExportResult(_Result):
    """Thread export document result."""

    document: dict[str, Any]


class ThreadLoadedListResult(_Result):
    """Loaded thread IDs list result."""

    thread_ids: list[str] = Field(validation_alias="threadIds")


class UnsupportedResult(_Result):
    """Empty result for unsupported methods."""
    pass


THREAD_METHOD_RESULT_MODELS: dict[str, type[BaseModel]] = {
    "thread/start": ThreadResult,
    "thread/resume": ThreadResult,
    "thread/fork": ThreadResult,
    "thread/read": ThreadResult,
    "thread/turns/list": ThreadPageResult,
    "thread/turns/items/list": UnsupportedResult,
    "thread/list": ThreadPageResult,
    "thread/export": ThreadExportResult,
    "thread/import": ThreadResult,
    "thread/name/set": ThreadResult,
    "thread/rollback": ThreadResult,
    "thread/loaded/list": ThreadLoadedListResult,
}
