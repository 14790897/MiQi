"""Typed request params for thread/* App Server methods."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from miqi.runtime.app_server import AppServerError


class _Params(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ThreadStartParams(_Params):
    """thread/start — create a new thread within a session."""

    title: str | None = None
    name: str | None = None
    thread_id: str | None = Field(default=None, validation_alias="threadId")
    ephemeral: bool = False
    cwd: str | None = None
    session_key: str | None = Field(default=None, validation_alias="sessionKey")
    session_id: str | None = Field(default=None, validation_alias="sessionId")

    @model_validator(mode="after")
    def _merge_title(self) -> "ThreadStartParams":
        if self.title is None and self.name is not None:
            self.title = self.name
        return self

    @field_validator("ephemeral", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        if not isinstance(value, bool):
            raise ValueError("ephemeral must be a boolean")
        return value

    @field_validator("title", "name", "cwd", mode="before")
    @classmethod
    def _optional_string(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, str):
            raise ValueError("must be a string")
        return value


class ThreadResumeParams(_Params):
    """thread/resume — resume an existing thread."""

    thread_id: str = Field(default="", validation_alias="threadId")
    exclude_turns: bool = Field(default=False, validation_alias="excludeTurns")
    items_view: str | None = Field(default=None, validation_alias="itemsView")
    session_key: str | None = Field(default=None, validation_alias="sessionKey")
    session_id: str | None = Field(default=None, validation_alias="sessionId")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadResumeParams":
        if not self.thread_id.strip():
            raise ValueError("threadId is required")
        return self

    @field_validator("thread_id", mode="before")
    @classmethod
    def _thread_id(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("threadId must be a non-empty string")
        return value

    @field_validator("exclude_turns", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        if not isinstance(value, bool):
            raise ValueError("excludeTurns must be a boolean")
        return value


class ThreadForkParams(_Params):
    """thread/fork — fork a thread from a source."""

    thread_id: str = Field(default="", validation_alias="threadId")
    title: str | None = None
    exclude_turns: bool = Field(default=False, validation_alias="excludeTurns")
    items_view: str | None = Field(default=None, validation_alias="itemsView")
    session_id: str | None = Field(default=None, validation_alias="sessionId")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadForkParams":
        if not self.thread_id.strip():
            raise ValueError("threadId is required")
        return self

    @field_validator("thread_id", mode="before")
    @classmethod
    def _thread_id(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("threadId must be a non-empty string")
        return value

    @field_validator("exclude_turns", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        if not isinstance(value, bool):
            raise ValueError("excludeTurns must be a boolean")
        return value


class ThreadReadParams(_Params):
    """thread/read — read a thread view."""

    thread_id: str = Field(default="", validation_alias="threadId")
    include_turns: bool = Field(default=False, validation_alias="includeTurns")
    items_view: str | None = Field(default=None, validation_alias="itemsView")
    session_id: str | None = Field(default=None, validation_alias="sessionId")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadReadParams":
        if not self.thread_id.strip():
            raise ValueError("threadId is required")
        return self

    @field_validator("thread_id", mode="before")
    @classmethod
    def _thread_id(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("threadId must be a non-empty string")
        return value

    @field_validator("include_turns", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        if not isinstance(value, bool):
            raise ValueError("includeTurns must be a boolean")
        return value


class ThreadTurnsListParams(_Params):
    """thread/turns/list — list turns for a thread."""

    thread_id: str = Field(default="", validation_alias="threadId")
    limit: int = 50
    cursor: str | None = None
    sort_direction: str | None = Field(default=None, validation_alias="sortDirection")
    items_view: str | None = Field(default=None, validation_alias="itemsView")
    session_id: str | None = Field(default=None, validation_alias="sessionId")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadTurnsListParams":
        if not self.thread_id.strip():
            raise ValueError("threadId is required")
        return self

    @field_validator("thread_id", mode="before")
    @classmethod
    def _thread_id(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("threadId must be a non-empty string")
        return value

    @field_validator("limit", mode="before")
    @classmethod
    def _limit(cls, value: Any) -> Any:
        if not isinstance(value, int):
            raise ValueError("limit must be an integer")
        if value < 1 or value > 500:
            raise ValueError("limit must be between 1 and 500")
        return value


class ThreadTurnsItemsListParams(_Params):
    """thread/turns/items/list — unsupported, validated before rejection."""

    thread_id: str | None = Field(default=None, validation_alias="threadId")

    @field_validator("thread_id", mode="before")
    @classmethod
    def _thread_id(cls, value: Any) -> Any:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("threadId must be a non-empty string")
        return value


class ThreadListParams(_Params):
    """thread/list — list stored threads."""

    archived: bool = False
    session_id: str | None = Field(default=None, validation_alias="sessionId")
    cwd: str | None = None
    search_term: str | None = Field(default=None, validation_alias="searchTerm")
    limit: int = 50
    cursor: str | None = None
    sort_direction: str | None = Field(default=None, validation_alias="sortDirection")

    @field_validator("archived", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        if not isinstance(value, bool):
            raise ValueError("archived must be a boolean")
        return value

    @field_validator("limit", mode="before")
    @classmethod
    def _limit(cls, value: Any) -> Any:
        if not isinstance(value, int):
            raise ValueError("limit must be an integer")
        if value < 1 or value > 500:
            raise ValueError("limit must be between 1 and 500")
        return value


class ThreadExportParams(_Params):
    """thread/export — export a thread as a document."""

    thread_id: str = Field(default="", validation_alias="threadId")
    session_id: str | None = Field(default=None, validation_alias="sessionId")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadExportParams":
        if not self.thread_id.strip():
            raise ValueError("threadId is required")
        return self

    @field_validator("thread_id", mode="before")
    @classmethod
    def _thread_id(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("threadId must be a non-empty string")
        return value


class ThreadImportParams(_Params):
    """thread/import — import a thread from a document."""

    document: dict[str, Any] | None = Field(default=None)
    session_id: str | None = Field(default=None, validation_alias="sessionId")
    session_key: str | None = Field(default=None, validation_alias="sessionKey")
    thread_id: str | None = Field(default=None, validation_alias="threadId")
    overwrite: bool = False
    include_turns: bool = Field(default=False, validation_alias="includeTurns")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadImportParams":
        if not isinstance(self.document, dict):
            raise ValueError("document is required and must be an object")
        return self

    @field_validator("overwrite", "include_turns", mode="before")
    @classmethod
    def _bool(cls, value: Any) -> Any:
        if not isinstance(value, bool):
            raise ValueError("must be a boolean")
        return value


class ThreadNameSetParams(_Params):
    """thread/name/set — rename a thread."""

    thread_id: str = Field(default="", validation_alias="threadId")
    name: str = ""

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadNameSetParams":
        if not self.thread_id.strip():
            raise ValueError("threadId is required")
        if not self.name.strip():
            raise ValueError("name is required")
        return self

    @field_validator("thread_id", "name", mode="before")
    @classmethod
    def _non_empty(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class ThreadRollbackParams(_Params):
    """thread/rollback — roll back turns in a thread."""

    thread_id: str = Field(default="", validation_alias="threadId")
    drop_last_turns: int = Field(default=1, validation_alias="dropLastTurns")
    num_turns: int | None = Field(default=None, validation_alias="numTurns")
    items_view: str | None = Field(default=None, validation_alias="itemsView")
    session_id: str | None = Field(default=None, validation_alias="sessionId")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadRollbackParams":
        if not self.thread_id.strip():
            raise ValueError("threadId is required")
        # If num_turns was provided and drop_last_turns is default (1),
        # use num_turns as the count
        if self.num_turns is not None and self.drop_last_turns == 1 and self.num_turns != 1:
            self.drop_last_turns = self.num_turns
        if self.drop_last_turns < 1:
            raise ValueError("dropLastTurns must be >= 1")
        return self

    @field_validator("thread_id", mode="before")
    @classmethod
    def _thread_id(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("threadId must be a non-empty string")
        return value

    @field_validator("drop_last_turns", "num_turns", mode="before")
    @classmethod
    def _int_positive(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, int):
            raise ValueError("must be an integer")
        return value


class ThreadLoadedListParams(_Params):
    """thread/loaded/list — list loaded thread IDs. Empty params."""
    pass


# ── compatibility methods ──────────────────────────────────────────────────


class ThreadCreateCompatParams(_Params):
    """thread.create — legacy create a thread in the active session."""

    title: str | None = None
    thread_id: str | None = Field(default=None, validation_alias="thread_id")

    @field_validator("title", "thread_id", mode="before")
    @classmethod
    def _optional_string(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, str):
            raise ValueError("must be a string")
        return value


class ThreadListCompatParams(_Params):
    """thread.list — legacy list threads. Empty params."""
    pass


class ThreadRenameCompatParams(_Params):
    """thread.rename — legacy rename a thread."""

    thread_id: str = Field(default="", validation_alias="thread_id")
    title: str = ""

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadRenameCompatParams":
        if not self.thread_id.strip():
            raise ValueError("thread_id is required")
        if not self.title.strip():
            raise ValueError("title is required")
        return self

    @field_validator("thread_id", "title", mode="before")
    @classmethod
    def _non_empty(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value


class ThreadArchiveCompatParams(_Params):
    """thread.archive — legacy archive a thread."""

    thread_id: str = Field(default="", validation_alias="thread_id")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadArchiveCompatParams":
        if not self.thread_id.strip():
            raise ValueError("thread_id is required")
        return self

    @field_validator("thread_id", mode="before")
    @classmethod
    def _non_empty(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("thread_id must be a non-empty string")
        return value


class ThreadDeleteCompatParams(_Params):
    """thread.delete — legacy delete a thread."""

    thread_id: str = Field(default="", validation_alias="thread_id")

    @model_validator(mode="after")
    def _check_required(self) -> "ThreadDeleteCompatParams":
        if not self.thread_id.strip():
            raise ValueError("thread_id is required")
        return self

    @field_validator("thread_id", mode="before")
    @classmethod
    def _non_empty(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("thread_id must be a non-empty string")
        return value


class ChatAbortParams(_Params):
    """chat.abort — abort the active turn in a session."""

    thread_id: str | None = Field(default=None, validation_alias="thread_id")

    @field_validator("thread_id", mode="before")
    @classmethod
    def _optional_string(cls, value: Any) -> Any:
        if value is not None and not isinstance(value, str):
            raise ValueError("thread_id must be a string")
        return value


THREAD_METHOD_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "thread/start": ThreadStartParams,
    "thread/resume": ThreadResumeParams,
    "thread/fork": ThreadForkParams,
    "thread/read": ThreadReadParams,
    "thread/turns/list": ThreadTurnsListParams,
    "thread/turns/items/list": ThreadTurnsItemsListParams,
    "thread/list": ThreadListParams,
    "thread/export": ThreadExportParams,
    "thread/import": ThreadImportParams,
    "thread/name/set": ThreadNameSetParams,
    "thread/rollback": ThreadRollbackParams,
    "thread/loaded/list": ThreadLoadedListParams,
    "thread.create": ThreadCreateCompatParams,
    "thread.list": ThreadListCompatParams,
    "thread.rename": ThreadRenameCompatParams,
    "thread.archive": ThreadArchiveCompatParams,
    "thread.delete": ThreadDeleteCompatParams,
    "chat.abort": ChatAbortParams,
}


def validate_thread_params(method: str, params: dict[str, Any]) -> BaseModel:
    model = THREAD_METHOD_PARAM_MODELS[method]
    try:
        return model.model_validate(params)
    except ValidationError as exc:
        raise AppServerError("Invalid params", code="INVALID_PARAMS") from exc
