"""Permission and sandbox policy types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FileSystemAccessMode(str, Enum):
    READ = "read"
    WRITE = "write"
    NONE = "none"


@dataclass
class FileSystemPathRule:
    """A filesystem access rule for a specific path."""
    path: str
    mode: FileSystemAccessMode
    recursive: bool = True


@dataclass
class FileSystemSandboxPolicy:
    """Filesystem sandbox policy composed of path rules."""
    rules: list[FileSystemPathRule] = field(default_factory=list)
    default_mode: FileSystemAccessMode = FileSystemAccessMode.READ
    deny_hidden: bool = True
    deny_git: bool = False


class NetworkSandboxPolicy(str, Enum):
    ALLOW_ALL = "allow_all"
    BLOCK_ALL = "block_all"
    ALLOW_LIST = "allow_list"


@dataclass
class SandboxPermissions:
    """Combined sandbox permissions for a tool execution."""
    filesystem: FileSystemSandboxPolicy = field(
        default_factory=FileSystemSandboxPolicy
    )
    network: NetworkSandboxPolicy = NetworkSandboxPolicy.ALLOW_ALL
    allow_host_network: list[str] = field(default_factory=list)
    env_passthrough: list[str] = field(default_factory=list)
    timeout_ms: int = 30_000
