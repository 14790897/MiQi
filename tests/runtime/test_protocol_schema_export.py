from __future__ import annotations

from miqi.runtime.protocol_registry import (
    MethodScope,
    MethodStability,
    ProtocolMethodSpec,
    ProtocolRegistry,
)


def test_registry_exports_json_schema_document():
    registry = ProtocolRegistry()
    registry.add(ProtocolMethodSpec(
        method="turn/start",
        stability=MethodStability.STABLE,
        scope=MethodScope.TURN,
        params_schema={"type": "object", "required": ["threadId"]},
        result_schema={"type": "object"},
    ))

    schema = registry.to_json_schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"] == "MiQi App Server Protocol Catalog"
    assert schema["type"] == "object"
    assert "methods" in schema["properties"]
    assert schema["x-miqi-protocol"]["version"] == 1
    assert schema["x-miqi-protocol"]["methods"][0]["method"] == "turn/start"


def test_protocol_specs_use_model_derived_params_schema():
    from miqi.runtime.filesystem_request_models import FsWriteFileParams
    from miqi.runtime.process_request_models import CommandExecParams
    from miqi.runtime.protocol_model_schema import params_schema_from_model
    from miqi.runtime.protocol_specs import COMMAND_EXEC, FS_WRITE_FILE

    assert COMMAND_EXEC.params_schema == params_schema_from_model(CommandExecParams)
    assert FS_WRITE_FILE.params_schema == params_schema_from_model(FsWriteFileParams)
    assert "dataBase64" in FS_WRITE_FILE.params_schema["properties"]
    assert sorted(FS_WRITE_FILE.params_schema["required"]) == ["dataBase64", "path"]
