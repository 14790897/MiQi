"""Tests for session request models."""

from __future__ import annotations

import pytest

from miqi.runtime.session_request_models import (
    SESSION_METHOD_PARAM_MODELS,
    validate_session_params,
)
from miqi.runtime.app_server import AppServerError


class TestAllMethodsExist:
    def test_all_9_methods_in_param_map(self):
        expected = {
            "sessions.list",
            "sessions.get",
            "sessions.delete",
            "sessions.archive",
            "sessions.unarchive",
            "sessions.list_archived",
            "sessions.get_tracked_files",
            "sessions.clear_tracked_files",
            "sessions.claim_legacy",
        }
        assert set(SESSION_METHOD_PARAM_MODELS) == expected


class TestSessionKeyAlias:
    def test_accepts_sessionKey(self):
        typed = validate_session_params("sessions.get", {"sessionKey": "abc"})
        assert typed.session_key == "abc"

    def test_accepts_session_key(self):
        typed = validate_session_params("sessions.get", {"session_key": "abc"})
        assert typed.session_key == "abc"


class TestBlankKeyRejected:
    def test_empty_key_rejected(self):
        with pytest.raises(AppServerError) as exc:
            validate_session_params("sessions.get", {"sessionKey": ""})
        assert exc.value.code == "INVALID_PARAMS"

    def test_missing_key_rejected(self):
        with pytest.raises(AppServerError) as exc:
            validate_session_params("sessions.get", {})
        assert exc.value.code == "INVALID_PARAMS"


class TestInvalidKeysRejected:
    def test_dot_dot_slash_rejected(self):
        with pytest.raises(AppServerError) as exc:
            validate_session_params("sessions.delete", {"sessionKey": "../x"})
        assert exc.value.code == "INVALID_PARAMS"

    def test_forward_slash_rejected(self):
        with pytest.raises(AppServerError) as exc:
            validate_session_params("sessions.archive", {"sessionKey": "a/b"})
        assert exc.value.code == "INVALID_PARAMS"

    def test_backslash_rejected(self):
        with pytest.raises(AppServerError) as exc:
            validate_session_params("sessions.get_tracked_files", {"sessionKey": "a\\b"})
        assert exc.value.code == "INVALID_PARAMS"

    def test_non_string_rejected(self):
        with pytest.raises(AppServerError) as exc:
            validate_session_params("sessions.claim_legacy", {"session_key": 123})
        assert exc.value.code == "INVALID_PARAMS"
