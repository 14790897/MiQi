from __future__ import annotations

import pytest

from miqi.runtime.app_server import AppServerError
from miqi.runtime.filesystem_request_models import (
    FsCopyParams,
    FsCreateDirectoryParams,
    FsReadFileParams,
    FsRemoveParams,
    FsUnwatchParams,
    FsWatchParams,
    FsWriteFileParams,
    FuzzyFileSearchParams,
    FuzzySessionStartParams,
    FuzzySessionStopParams,
    FuzzySessionUpdateParams,
    validate_filesystem_params,
)


def test_fs_read_file_requires_path_string():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FsReadFileParams, {"path": 123})

    assert exc.value.code == "INVALID_PARAMS"


def test_fs_write_file_requires_data_base64_string():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FsWriteFileParams, {
            "path": "/tmp/file.txt",
            "dataBase64": 123,
        })

    assert exc.value.code == "INVALID_PARAMS"


def test_fs_create_directory_defaults_recursive_true():
    params = validate_filesystem_params(FsCreateDirectoryParams, {"path": "/tmp/dir"})

    assert params.path == "/tmp/dir"
    assert params.recursive is True


def test_fs_create_directory_rejects_string_recursive():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FsCreateDirectoryParams, {
            "path": "/tmp/dir",
            "recursive": "false",
        })

    assert exc.value.code == "INVALID_PARAMS"


def test_fs_remove_defaults_recursive_and_force_true():
    params = validate_filesystem_params(FsRemoveParams, {"path": "/tmp/file.txt"})

    assert params.recursive is True
    assert params.force is True


def test_fs_remove_rejects_string_force():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FsRemoveParams, {
            "path": "/tmp/file.txt",
            "force": "false",
        })

    assert exc.value.code == "INVALID_PARAMS"


def test_fs_copy_defaults_recursive_false():
    params = validate_filesystem_params(FsCopyParams, {
        "sourcePath": "/tmp/a",
        "destinationPath": "/tmp/b",
    })

    assert params.source_path == "/tmp/a"
    assert params.destination_path == "/tmp/b"
    assert params.recursive is False


def test_fs_copy_rejects_string_recursive():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FsCopyParams, {
            "sourcePath": "/tmp/a",
            "destinationPath": "/tmp/b",
            "recursive": "true",
        })

    assert exc.value.code == "INVALID_PARAMS"


def test_fs_watch_requires_non_empty_watch_id():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FsWatchParams, {
            "watchId": "   ",
            "path": "/tmp",
        })

    assert exc.value.code == "INVALID_PARAMS"


def test_fs_unwatch_rejects_missing_watch_id():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FsUnwatchParams, {})

    assert exc.value.code == "INVALID_PARAMS"


def test_fuzzy_file_search_requires_roots_list():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FuzzyFileSearchParams, {
            "query": "readme",
            "roots": "/tmp",
        })

    assert exc.value.code == "INVALID_PARAMS"


def test_fuzzy_file_search_rejects_non_string_root():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FuzzyFileSearchParams, {
            "query": "readme",
            "roots": [123],
        })

    assert exc.value.code == "INVALID_PARAMS"


def test_fuzzy_session_start_requires_session_id_and_roots():
    params = validate_filesystem_params(FuzzySessionStartParams, {
        "sessionId": "search-1",
        "roots": ["/tmp"],
    })

    assert params.session_id == "search-1"
    assert params.roots == ["/tmp"]


def test_fuzzy_session_update_requires_query_string():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FuzzySessionUpdateParams, {
            "sessionId": "search-1",
            "query": 123,
        })

    assert exc.value.code == "INVALID_PARAMS"


def test_fuzzy_session_stop_rejects_non_string_session_id():
    with pytest.raises(AppServerError) as exc:
        validate_filesystem_params(FuzzySessionStopParams, {"sessionId": 123})

    assert exc.value.code == "INVALID_PARAMS"


def test_fs_write_file_accepts_empty_data_base64():
    params = validate_filesystem_params(FsWriteFileParams, {
        "path": "/tmp/file.txt",
        "dataBase64": "",
    })

    assert params.path == "/tmp/file.txt"
    assert params.data_base64 == ""
