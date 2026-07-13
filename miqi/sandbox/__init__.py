"""Sandbox module — per-session sandbox isolation for MiQi agent commands.

Provides two sandbox providers:

* :class:`BwrapSandbox` — lightweight, zero-dependency bubblewrap isolation (default)
* :class:`DockerSandbox` — Docker/OpenSandbox-backed container isolation (experimental)
"""

from miqi.sandbox.bwrap import BwrapSandbox
from miqi.sandbox.docker_sandbox import DockerSandbox
from miqi.sandbox.manager import SandboxManager

__all__ = ["BwrapSandbox", "DockerSandbox", "SandboxManager"]
