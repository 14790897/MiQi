from __future__ import annotations

import pytest

from miqi.runtime.app_protocol import (
    AppErrorEnvelope,
    AppEventEnvelope,
    AppRequestEnvelope,
    AppResponseEnvelope,
)


def test_request_envelope_accepts_current_wire_shape():
    req = AppRequestEnvelope.model_validate({
        "id": "req-1",
        "method": "turn/start",
        "params": {"threadId": "thread-1", "input": [{"type": "text", "text": "hi"}]},
    })

    assert req.id == "req-1"
    assert req.method == "turn/start"
    assert req.params["threadId"] == "thread-1"


def test_request_envelope_rejects_missing_method():
    with pytest.raises(ValueError):
        AppRequestEnvelope.model_validate({"id": "req-1", "params": {}})


def test_response_envelope_serializes_current_wire_shape():
    response = AppResponseEnvelope(id="req-1", result={"ok": True})

    assert response.model_dump(exclude_none=True) == {
        "id": "req-1",
        "result": {"ok": True},
    }


def test_error_envelope_serializes_code_and_recoverable():
    error = AppErrorEnvelope(
        id="req-1",
        error="Invalid params",
        code="INVALID_PARAMS",
        recoverable=False,
    )

    assert error.model_dump(exclude_none=True) == {
        "id": "req-1",
        "error": "Invalid params",
        "code": "INVALID_PARAMS",
        "recoverable": False,
    }


def test_event_envelope_allows_push_event_without_id():
    event = AppEventEnvelope(
        type="fs/changed",
        data={"watchId": "watch-1"},
    )

    assert event.model_dump(exclude_none=True) == {
        "type": "fs/changed",
        "data": {"watchId": "watch-1"},
    }
