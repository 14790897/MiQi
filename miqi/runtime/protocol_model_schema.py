"""Helpers for deriving protocol catalog schemas from typed request models."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from miqi.runtime.protocol_registry import (
    MethodScope,
    MethodStability,
    ProtocolMethodSpec,
)


_INTERNAL_MODEL_FIELDS = {
    "cwd_raw",
}


def _external_field_name(name: str, field: Any) -> str:
    alias = field.validation_alias
    return str(alias) if alias is not None else name


def _drop_internal_fields(schema: dict[str, Any], model: type[BaseModel]) -> dict[str, Any]:
    result = deepcopy(schema)
    properties = dict(result.get("properties") or {})
    required = list(result.get("required") or [])

    for name in model.model_fields:
        if name not in _INTERNAL_MODEL_FIELDS:
            continue
        # Remove the internal Python name from the schema.
        # With by_alias=True the schema keys are wire names, so this is
        # typically a no-op — but it is defense-in-depth.
        properties.pop(name, None)
        if name in required:
            required.remove(name)

    if properties:
        result["properties"] = properties
    else:
        result.pop("properties", None)

    if required:
        result["required"] = sorted(required)
    else:
        result.pop("required", None)

    return result


def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(schema)
    result["type"] = "object"
    result["additionalProperties"] = True

    if "required" in result:
        result["required"] = sorted(result["required"])

    # Pydantic emits class titles that make schemas noisy and do not add
    # contract value for protocol/catalog consumers.
    result.pop("title", None)

    properties = result.get("properties")
    if isinstance(properties, dict):
        for prop in properties.values():
            if isinstance(prop, dict):
                prop.pop("title", None)

    return result


def params_schema_from_model(model: type[BaseModel]) -> dict[str, Any]:
    """Return a catalog-ready paramsSchema for a Pydantic request model.

    The schema uses external wire aliases and keeps additionalProperties=true,
    matching the current request models' extra="allow" behavior.
    """
    raw = model.model_json_schema(by_alias=True)
    without_internal = _drop_internal_fields(raw, model)
    return _normalize_schema(without_internal)


def model_spec(
    method: str,
    model: type[BaseModel],
    *,
    scope: MethodScope,
    stability: MethodStability = MethodStability.STABLE,
    result_schema: dict[str, Any] | None = None,
    emits: list[str] | None = None,
    description: str | None = None,
) -> ProtocolMethodSpec:
    """Create a ProtocolMethodSpec whose paramsSchema is derived from *model*."""
    return ProtocolMethodSpec(
        method=method,
        stability=stability,
        scope=scope,
        params_schema=params_schema_from_model(model),
        result_schema=result_schema or {"type": "object", "additionalProperties": True},
        emits=emits or [],
        description=description,
    )
