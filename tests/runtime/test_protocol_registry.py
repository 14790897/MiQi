from __future__ import annotations

import pytest

from miqi.runtime.protocol_registry import (
    MethodScope,
    MethodStability,
    ProtocolMethodSpec,
    ProtocolRegistry,
)


def test_method_spec_exports_minimal_json():
    spec = ProtocolMethodSpec(
        method="turn/start",
        stability=MethodStability.STABLE,
        scope=MethodScope.TURN,
        params_schema={"type": "object", "required": ["threadId"]},
        result_schema={"type": "object"},
        emits=["turn/started", "turn/completed"],
    )

    assert spec.to_json() == {
        "method": "turn/start",
        "stability": "stable",
        "scope": "turn",
        "paramsSchema": {"type": "object", "required": ["threadId"]},
        "resultSchema": {"type": "object"},
        "emits": ["turn/started", "turn/completed"],
        "eventSchemas": {},
        "deprecatedBy": None,
        "description": None,
    }


def test_method_spec_rejects_empty_method():
    with pytest.raises(ValueError):
        ProtocolMethodSpec(method="", stability=MethodStability.STABLE, scope=MethodScope.SESSION)


def test_registry_rejects_duplicate_specs():
    registry = ProtocolRegistry()
    spec = ProtocolMethodSpec(
        method="initialize",
        stability=MethodStability.STABLE,
        scope=MethodScope.CONNECTION,
    )

    registry.add(spec)

    with pytest.raises(ValueError):
        registry.add(spec)


def test_registry_exports_sorted_catalog():
    registry = ProtocolRegistry()
    registry.add(ProtocolMethodSpec(
        method="turn/start",
        stability=MethodStability.STABLE,
        scope=MethodScope.TURN,
    ))
    registry.add(ProtocolMethodSpec(
        method="initialize",
        stability=MethodStability.STABLE,
        scope=MethodScope.CONNECTION,
    ))

    catalog = registry.to_catalog()

    assert catalog["version"] == 1
    assert [m["method"] for m in catalog["methods"]] == ["initialize", "turn/start"]
