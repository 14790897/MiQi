"""Typed App Server wire envelopes.

These models describe MiQi's existing App Server wire shape. They do not
change transport behavior by themselves; BridgeRuntimeLoop still accepts
the same JSON objects it accepts today.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppRequestEnvelope(BaseModel):
    """Incoming client request envelope."""

    model_config = ConfigDict(extra="allow")

    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("method")
    @classmethod
    def _method_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("method must not be empty")
        return value


class AppResponseEnvelope(BaseModel):
    """Successful response envelope."""

    model_config = ConfigDict(extra="forbid")

    id: str | int | None = None
    result: Any = Field(default_factory=dict)


class AppErrorEnvelope(BaseModel):
    """Error response envelope."""

    model_config = ConfigDict(extra="forbid")

    id: str | int | None = None
    error: str
    code: str = "INTERNAL"
    recoverable: bool = False
    retry_after_ms: int | None = None


class AppEventEnvelope(BaseModel):
    """Server event envelope used by bridge transports."""

    model_config = ConfigDict(extra="forbid")

    id: str | int | None = None
    type: str
    data: Any = Field(default_factory=dict)
