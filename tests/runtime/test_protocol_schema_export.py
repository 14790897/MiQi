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
