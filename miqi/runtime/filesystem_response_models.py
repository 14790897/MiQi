"""Typed result and event payload models for filesystem/search App Server methods."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _ResponseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class EmptyResult(_ResponseModel):
    pass


class FsReadFileResult(_ResponseModel):
    data_base64: str = Field(serialization_alias="dataBase64")


class FsMetadataResult(_ResponseModel):
    is_directory: bool = Field(serialization_alias="isDirectory")
    is_file: bool = Field(serialization_alias="isFile")
    is_symlink: bool = Field(serialization_alias="isSymlink")
    created_at_ms: int = Field(serialization_alias="createdAtMs")
    modified_at_ms: int = Field(serialization_alias="modifiedAtMs")


class DirectoryEntry(_ResponseModel):
    file_name: str = Field(serialization_alias="fileName")
    is_directory: bool = Field(serialization_alias="isDirectory")
    is_file: bool = Field(serialization_alias="isFile")


class FsReadDirectoryResult(_ResponseModel):
    entries: list[DirectoryEntry]


class FsWatchResult(_ResponseModel):
    path: str


class FuzzyMatch(_ResponseModel):
    root: str
    path: str
    match_type: str
    file_name: str
    score: int
    indices: list[int]


class FuzzyFileSearchResult(_ResponseModel):
    files: list[FuzzyMatch]


class FsChangedEvent(_ResponseModel):
    watch_id: str = Field(serialization_alias="watchId")
    changed_paths: list[str] = Field(serialization_alias="changedPaths")


class FuzzySessionUpdatedEvent(_ResponseModel):
    session_id: str = Field(serialization_alias="sessionId")
    query: str
    files: list[FuzzyMatch]


class FuzzySessionCompletedEvent(_ResponseModel):
    session_id: str = Field(serialization_alias="sessionId")


FILESYSTEM_METHOD_RESULT_MODELS = {
    "fs/readFile": FsReadFileResult,
    "fs/writeFile": EmptyResult,
    "fs/createDirectory": EmptyResult,
    "fs/getMetadata": FsMetadataResult,
    "fs/readDirectory": FsReadDirectoryResult,
    "fs/remove": EmptyResult,
    "fs/copy": EmptyResult,
    "fs/watch": FsWatchResult,
    "fs/unwatch": EmptyResult,
    "fuzzyFileSearch": FuzzyFileSearchResult,
    "fuzzyFileSearch/sessionStart": EmptyResult,
    "fuzzyFileSearch/sessionUpdate": EmptyResult,
    "fuzzyFileSearch/sessionStop": EmptyResult,
}


FILESYSTEM_EVENT_MODELS = {
    "fs/changed": FsChangedEvent,
    "fuzzyFileSearch/sessionUpdated": FuzzySessionUpdatedEvent,
    "fuzzyFileSearch/sessionCompleted": FuzzySessionCompletedEvent,
}
