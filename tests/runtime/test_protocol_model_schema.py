from __future__ import annotations

from miqi.runtime.filesystem_request_models import FsWriteFileParams
from miqi.runtime.process_request_models import CommandExecParams
from miqi.runtime.protocol_model_schema import params_schema_from_model
from miqi.runtime.turn_request_models import TurnStartParams


def test_params_schema_uses_external_alias_names():
    schema = params_schema_from_model(TurnStartParams)

    assert schema["type"] == "object"
    assert "threadId" in schema["properties"]
    assert "clientUserMessageId" in schema["properties"]
    assert "thread_id" not in schema["properties"]
    assert "client_user_message_id" not in schema["properties"]
    assert sorted(schema["required"]) == ["input", "threadId"]


def test_params_schema_preserves_extra_allowed_contract():
    schema = params_schema_from_model(FsWriteFileParams)

    assert schema["additionalProperties"] is True


def test_params_schema_exposes_required_and_optional_fields():
    schema = params_schema_from_model(CommandExecParams)

    assert schema["required"] == ["command"]
    assert "command" in schema["properties"]
    assert "processId" in schema["properties"]
    assert "cwd" in schema["properties"]
    assert "timeoutMs" in schema["properties"]
    assert "outputBytesCap" in schema["properties"]


def test_params_schema_skips_internal_runtime_fields():
    schema = params_schema_from_model(CommandExecParams)

    assert "cwd" in schema["properties"]
    assert "cwd_raw" not in schema["properties"]


def test_params_schema_is_deterministic():
    first = params_schema_from_model(FsWriteFileParams)
    second = params_schema_from_model(FsWriteFileParams)

    assert first == second
