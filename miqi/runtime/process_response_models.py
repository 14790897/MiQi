"""Typed result and event payload models for command/process App Server methods."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _ResponseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class EmptyResult(_ResponseModel):
    pass


class CommandExecResult(_ResponseModel):
    exit_code: int = Field(serialization_alias="exitCode")
    stdout: str
    stderr: str
    stdout_cap_reached: bool = Field(serialization_alias="stdoutCapReached")
    stderr_cap_reached: bool = Field(serialization_alias="stderrCapReached")
    duration_ms: int = Field(serialization_alias="durationMs")
    termination_reason: str | None = Field(serialization_alias="terminationReason")


class CommandExecOutputDeltaEvent(_ResponseModel):
    process_id: str = Field(serialization_alias="processId")
    stream: str
    delta_base64: str = Field(serialization_alias="deltaBase64")
    cap_reached: bool = Field(serialization_alias="capReached")


class ProcessOutputDeltaEvent(_ResponseModel):
    process_handle: str = Field(serialization_alias="processHandle")
    stream: str
    delta_base64: str = Field(serialization_alias="deltaBase64")
    cap_reached: bool = Field(serialization_alias="capReached")


class ProcessExitedEvent(_ResponseModel):
    process_handle: str = Field(serialization_alias="processHandle")
    exit_code: int = Field(serialization_alias="exitCode")
    stdout: str
    stderr: str
    stdout_cap_reached: bool = Field(serialization_alias="stdoutCapReached")
    stderr_cap_reached: bool = Field(serialization_alias="stderrCapReached")
    duration_ms: int = Field(serialization_alias="durationMs")
    termination_reason: str | None = Field(serialization_alias="terminationReason")


PROCESS_METHOD_RESULT_MODELS = {
    "command/exec": CommandExecResult,
    "command/exec/write": EmptyResult,
    "command/exec/resize": EmptyResult,
    "command/exec/terminate": EmptyResult,
    "process/spawn": EmptyResult,
    "process/writeStdin": EmptyResult,
    "process/resizePty": EmptyResult,
    "process/kill": EmptyResult,
}


PROCESS_EVENT_MODELS = {
    "command/exec/outputDelta": CommandExecOutputDeltaEvent,
    "process/outputDelta": ProcessOutputDeltaEvent,
    "process/exited": ProcessExitedEvent,
}
