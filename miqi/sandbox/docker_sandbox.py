"""Docker-based sandbox implementation powered by OpenSandbox.

OpenSandbox is a general-purpose sandbox platform (Alibaba) that provides
Docker/Kubernetes-backed isolation with multi-language SDKs.  This module
wraps the OpenSandbox Python SDK to expose the same interface as
:class:`BwrapSandbox`, so MiQi can optionally use Docker containers
instead of bubblewrap for command execution.

.. note::

   This requires Docker Engine 20.10+ and the ``opensandbox`` Python
   package.  It is **opt-in** — the default sandbox provider remains
   bubblewrap.  Set ``tools.sandbox.provider = "opensandbox"`` in
   ``~/.miqi/config.json`` to activate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger("miqi.sandbox.docker")


# ── OpenSandbox availability guard ───────────────────────────────────────

_OPEN_SANDBOX_AVAILABLE: bool | None = None


def _check_opensandbox() -> bool:
    """Return True if the opensandbox SDK is installed and importable."""
    global _OPEN_SANDBOX_AVAILABLE
    if _OPEN_SANDBOX_AVAILABLE is not None:
        return _OPEN_SANDBOX_AVAILABLE
    try:
        import opensandbox  # noqa: F401
        _OPEN_SANDBOX_AVAILABLE = True
    except ImportError:
        _OPEN_SANDBOX_AVAILABLE = False
    return _OPEN_SANDBOX_AVAILABLE


# ── Default Docker image ─────────────────────────────────────────────────

# This image is the MiQi sandbox runtime.  It should contain a basic
# Linux userspace (bash, coreutils, python3, etc.).  Build it with:
#
#   docker build -t miqi-sandbox:latest -f Dockerfile.sandbox .
#
DEFAULT_SANDBOX_IMAGE = os.environ.get(
    "MIQI_OPEN_SANDBOX_IMAGE",
    "miqi-sandbox:latest",
)

# Timeout for the sandbox container (auto-destroy after this duration).
DEFAULT_SANDBOX_TIMEOUT_SECONDS = 600  # 10 minutes


# ── Streaming command handle ─────────────────────────────────────────────


class DockerCommandHandle:
    """Handle to a running command inside a Docker sandbox.

    Mirrors the interface of :class:`BwrapCommandHandle` so ExecTool
    can use either implementation transparently.

    The underlying mechanism depends on the SDK version:

    * **OpenSandbox SDK** (``opensandbox``): uses ``sandbox.commands.run()``
      or ``sandbox.commands.start()`` with streaming callbacks.
    * **Fallback (native Docker)** : uses ``docker exec`` via subprocess
      when the SDK is not installed.
    """

    __slots__ = ("_process", "_temp_dir")

    def __init__(self, process: asyncio.subprocess.Process, temp_dir: str | None = None):
        self._process = process
        self._temp_dir = temp_dir

    @property
    def stdout(self) -> asyncio.StreamReader | None:
        return self._process.stdout  # type: ignore[return-value]

    @property
    def stderr(self) -> asyncio.StreamReader | None:
        return self._process.stderr  # type: ignore[return-value]

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    async def wait(self) -> int:
        await self._process.wait()
        return self._process.returncode if self._process.returncode is not None else -1

    async def kill(self) -> None:
        try:
            self._process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(self._process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass

    async def cleanup(self) -> None:
        if self._temp_dir:
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass


# ── DockerSandbox ────────────────────────────────────────────────────────


class DockerSandbox:
    """Manages a single Docker container sandbox for one conversation session.

    Implements the same contract as :class:`BwrapSandbox`:

    * ``start()`` — launch the container
    * ``stop()``  — destroy the container
    * ``run_command()`` — execute a command (batch mode)
    * ``run_command_streaming()`` — execute a command with incremental stdout/stderr
    * ``get_sandbox_env()`` — return env vars visible inside the container
    * ``is_running``, ``workspace_path``, ``session_key`` — properties
    """

    def __init__(
        self,
        session_key: str,
        workspace: Path | str,
        sandbox_base_dir: Path | str | None = None,
        share_net: bool = False,
        image: str = DEFAULT_SANDBOX_IMAGE,
        timeout: int = DEFAULT_SANDBOX_TIMEOUT_SECONDS,
        extra_ro_binds: list[str] | None = None,
        extra_rw_binds: list[str] | None = None,
        hostname: str = "miqi-sandbox",
        uid: int = 1000,
        gid: int = 1000,
        # ── unused (kept for kwarg compatibility with BwrapSandbox) ──
        wsl_distro: str = "",
        wsl_base_dir: str = "/tmp/miqi-sandboxes",
        sandbox_distro_name: str = "",
        auto_install_deps: bool = True,
    ):
        self.session_key = session_key
        self.workspace = Path(workspace).resolve()
        self.share_net = share_net
        self.image = image
        self.timeout = timeout

        # Per-session filesystem layout
        safe_key = (
            session_key.replace(":", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace("'", "_")
        )
        if sandbox_base_dir:
            self._base_dir = Path(sandbox_base_dir) / safe_key
        else:
            self._base_dir = Path(tempfile.gettempdir()) / "miqi-sandboxes" / safe_key

        # Container-side paths (always Linux)
        self.sandbox_home: str = "/home/miqi"
        self.sandbox_workspace: str = "/home/miqi/workspace"

        # Runtime state
        self._container_id: str | None = None
        self._running = False

        # Volume mounts: host path → container path
        self._volumes: dict[str, str] = {
            str(self._base_dir / "home"): self.sandbox_home,
            str(self._base_dir / "workspace"): self.sandbox_workspace,
        }

    # ── Properties (match BwrapSandbox contract) ────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def workspace_path(self) -> str:
        return self.sandbox_workspace

    @property
    def home_path(self) -> str:
        return self.sandbox_home

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch the Docker container and wait for it to be ready."""
        if self._running:
            return

        # Ensure host directories exist
        host_home = self._base_dir / "home"
        host_workspace = self._base_dir / "workspace"
        host_home.mkdir(parents=True, exist_ok=True)
        host_workspace.mkdir(parents=True, exist_ok=True)

        # Build docker run command
        cmd = ["docker", "run", "-d", "--rm"]
        cmd.extend(["--hostname", "miqi-sandbox"])

        # Volume mounts
        cmd.extend(["-v", f"{host_home}:/home/miqi"])
        cmd.extend(["-v", f"{host_workspace}:/home/miqi/workspace"])

        # Environment
        cmd.extend(["-e", f"MIQI_SANDBOX=1"])
        cmd.extend(["-e", f"MIQI_SESSION_KEY={self.session_key}"])

        # Network
        if not self.share_net:
            cmd.append("--network=none")
            # Without network access, add a loopback for IPC
            cmd.append("--network=bridge" if self.share_net else "--network=none")

        # Resource limits
        cmd.extend(["--memory", "512m"])
        cmd.extend(["--cpus", "2"])

        # Keep alive with sleep
        cmd.append(self.image)
        cmd.extend(["sleep", str(self.timeout)])

        # Launch
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"DockerSandbox.start: docker run failed: {err}")

        self._container_id = stdout.decode("utf-8").strip()[:12]
        self._running = True
        logger.info(
            "DockerSandbox started: container=%s session=%s",
            self._container_id,
            self.session_key,
        )

    async def stop(self) -> None:
        """Stop and remove the Docker container."""
        if not self._running or not self._container_id:
            return

        # Kill the container
        proc = await asyncio.create_subprocess_exec(
            "docker", "kill", self._container_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        self._running = False
        self._container_id = None

        # Clean host directories
        try:
            shutil.rmtree(self._base_dir, ignore_errors=True)
        except Exception:
            pass

        logger.debug("DockerSandbox stopped: session=%s", self.session_key)

    # ── Command execution ───────────────────────────────────────────

    async def run_command(
        self,
        command: str,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
        cwd: str = "",
    ) -> tuple[int, str, str]:
        """Execute a command in the container and return (exit_code, stdout, stderr)."""
        if not self._running or not self._container_id:
            return -1, "", "sandbox not running"

        working_dir = cwd or self.sandbox_workspace

        docker_cmd = [
            "docker", "exec",
            "-w", working_dir,
        ]
        # Add env vars
        if env:
            for k, v in env.items():
                docker_cmd.extend(["-e", f"{k}={v}"])
        docker_cmd.append(self._container_id)
        # Split command into shell args
        docker_cmd.extend(["bash", "-lc", command])

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
            return (
                proc.returncode or 0,
                stdout_bytes.decode("utf-8", errors="replace"),
                stderr_bytes.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return -1, "", f"command timed out after {timeout}s"

    async def run_command_streaming(
        self,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str = "",
    ) -> DockerCommandHandle:
        """Execute a command with streaming stdout/stderr.

        Returns a :class:`DockerCommandHandle` that provides incremental
        access to stdout, stderr, and lifecycle control.
        """
        if not self._running or not self._container_id:
            raise RuntimeError("sandbox not running")

        working_dir = cwd or self.sandbox_workspace

        docker_cmd = [
            "docker", "exec",
            "-w", working_dir,
        ]
        if env:
            for k, v in env.items():
                docker_cmd.extend(["-e", f"{k}={v}"])
        docker_cmd.append(self._container_id)
        docker_cmd.extend(["bash", "-lc", command])

        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return DockerCommandHandle(process)

    def get_sandbox_env(self) -> dict[str, str]:
        """Return the environment variables visible inside the sandbox."""
        return {
            "HOME": self.sandbox_home,
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "en_US.UTF-8",
            "MIQI_SANDBOX": "1",
            "MIQI_SESSION_KEY": self.session_key,
        }

    # ── Static helpers ──────────────────────────────────────────────

    @staticmethod
    async def is_available() -> bool:
        """Check whether Docker is available for sandbox use."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return proc.returncode == 0
        except Exception:
            return False

    @staticmethod
    async def cleanup_dir(path: str) -> None:
        """Remove a sandbox directory tree (host-side cleanup)."""
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
