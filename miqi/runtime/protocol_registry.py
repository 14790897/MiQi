"""Protocol method metadata and catalog export."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MethodStability(str, Enum):
    STABLE = "stable"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"
    LEGACY = "legacy"


class MethodScope(str, Enum):
    CONNECTION = "connection"
    SESSION = "session"
    THREAD = "thread"
    TURN = "turn"
    PROCESS = "process"
    FILESYSTEM = "filesystem"
    DEBUG = "debug"


@dataclass(frozen=True)
class ProtocolMethodSpec:
    """Metadata for one App Server method."""

    method: str
    stability: MethodStability
    scope: MethodScope
    params_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    result_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    emits: list[str] = field(default_factory=list)
    event_schemas: dict[str, dict[str, Any]] = field(default_factory=dict)
    deprecated_by: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.method.strip():
            raise ValueError("method must not be empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "stability": self.stability.value,
            "scope": self.scope.value,
            "paramsSchema": self.params_schema,
            "resultSchema": self.result_schema,
            "emits": list(self.emits),
            "eventSchemas": dict(self.event_schemas),
            "deprecatedBy": self.deprecated_by,
            "description": self.description,
        }


class ProtocolRegistry:
    """In-memory registry of protocol method metadata."""

    def __init__(self) -> None:
        self._specs: dict[str, ProtocolMethodSpec] = {}

    def add(self, spec: ProtocolMethodSpec) -> None:
        if spec.method in self._specs:
            raise ValueError(f"Duplicate protocol method spec: {spec.method}")
        self._specs[spec.method] = spec

    def get(self, method: str) -> ProtocolMethodSpec | None:
        return self._specs.get(method)

    def methods(self) -> set[str]:
        return set(self._specs)

    def to_catalog(self) -> dict[str, Any]:
        return {
            "version": 1,
            "methods": [
                self._specs[name].to_json()
                for name in sorted(self._specs)
            ],
        }

    def to_json_schema(self) -> dict[str, Any]:
        """Return a JSON Schema document embedding the current protocol catalog."""
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "MiQi App Server Protocol Catalog",
            "type": "object",
            "required": ["version", "methods"],
            "properties": {
                "version": {"type": "integer"},
                "methods": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["method", "stability", "scope", "paramsSchema", "resultSchema"],
                        "properties": {
                            "method": {"type": "string"},
                            "stability": {"type": "string"},
                            "scope": {"type": "string"},
                            "paramsSchema": {"type": "object"},
                            "resultSchema": {"type": "object"},
                            "emits": {"type": "array", "items": {"type": "string"}},
                            "deprecatedBy": {"type": ["string", "null"]},
                            "description": {"type": ["string", "null"]},
                        },
                    },
                },
            },
            "x-miqi-protocol": self.to_catalog(),
        }


def legacy_method_spec(method: str) -> ProtocolMethodSpec:
    """Create a placeholder spec for methods not yet typed."""

    return ProtocolMethodSpec(
        method=method,
        stability=MethodStability.LEGACY,
        scope=MethodScope.SESSION,
        description="Legacy untyped method; migrate to an explicit spec in a later plan.",
    )
