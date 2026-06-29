from __future__ import annotations

from miqi.runtime.core_response_models import (
    CORE_METHOD_RESULT_MODELS,
    ConfigBatchWriteResult,
    InitializeResult,
    PythonCheckResult,
    StatusResult,
)
from miqi.runtime.protocol_model_schema import result_schema_from_model


def test_core_result_map_contains_plan69_methods():
    assert set(CORE_METHOD_RESULT_MODELS) == {
        "initialize",
        "initialized",
        "status",
        "python.check",
        "config/read",
        "config/batchWrite",
        "config.get",
        "config.update",
        "model/list",
        "modelProvider/capabilities/read",
        "experimentalFeature/list",
        "experimentalFeature/enablement/set",
        "permissionProfile/list",
    }


def test_status_result_schema_uses_wire_fields():
    schema = result_schema_from_model(StatusResult)

    assert set(schema["required"]) == {"status", "configured", "python_version"}
    assert schema["properties"]["status"]["type"] == "string"
    assert schema["properties"]["configured"]["type"] == "boolean"


def test_python_check_result_schema():
    schema = result_schema_from_model(PythonCheckResult)

    assert set(schema["required"]) == {"ok", "python_version", "issues", "config_exists"}
    assert schema["properties"]["issues"]["items"]["type"] == "string"


def test_initialize_result_schema_keeps_codex_home_alias():
    schema = result_schema_from_model(InitializeResult)

    assert "miqiHome" in schema["properties"]
    assert "codexHome" in schema["properties"]
    assert "clientId" in schema["properties"]


def test_config_batch_write_result_schema():
    schema = result_schema_from_model(ConfigBatchWriteResult)

    assert set(schema["required"]) == {"saved", "applied", "propagatedSessions"}
    assert schema["properties"]["propagatedSessions"]["type"] == "integer"
