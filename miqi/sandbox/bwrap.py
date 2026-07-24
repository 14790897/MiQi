"""Bubblewrap (bwrap) sandbox — creates per-session isolated environments.

Supports two execution modes:
1. **Native Linux** — runs bwrap directly
2. **Windows + WSL** — detects WSL availability and runs bwrap inside WSL

Each conversation gets its own mount namespace with:
- A writable overlay (tmpfs) for /tmp, /home/miqi/workspace
- Read-only bind mounts for /usr, /lib, /bin, etc.
- A per-session home directory with its own copy of the workspace
- Network isolation (unshare-net) by default
- PID namespace isolation (unshare-pid)

Usage:
    sandbox = BwrapSandbox(session_key="feishu:oc_123", workspace="/path/to/workspace")
    await sandbox.start()

    # Batch (legacy) — returns everything at once:
    exit_code, stdout, stderr = await sandbox.run_command("ls -la")

    # Streaming (Phase 33.2) — incremental stdout/stderr, cancel support:
    handle = await sandbox.run_command_streaming("long-running-cmd")
    while True:
        chunk = await handle.stdout.read(4096)
        if not chunk:
            break
        print(chunk.decode())
    await handle.wait()
    await handle.cleanup()

    await sandbox.stop()
"""

from __future__ import annotations

# pylint: disable=no-member,import-error
# Linux-specific APIs (os.killpg, signal.SIGKILL, os.getpgid) and
# loguru are only available on the target platform / in the WSL venv.

import asyncio
import os
import platform
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from loguru import logger

from miqi.runtime.workspace_logging import append_workspace_log


class BwrapSandboxError(Exception):
    """Error raised when bwrap operations fail."""


_auto_install_cache: dict[str, bool] = {}
"""Cache auto-install results per distro to avoid repeated apt-get calls."""

import threading
_install_lock = threading.Lock()
"""Serialize _ensure_wsl_deps to prevent concurrent apt-get.

When sandbox init is deferred to background (after the bridge ready
signal), a file_tool request may also trigger _ensure_wsl_deps via the
lazy check in SandboxManager.get_or_create().  Without a lock two
apt-get processes race on the dpkg lock and one fails.  This lock
makes the second caller wait for the first install, then re-check with
a quick ``which bwrap`` that succeeds immediately.
"""


class BwrapCommandHandle:
    """Handle to a running command inside the bwrap sandbox.

    Provides incremental access to stdout/stderr via :class:`asyncio.StreamReader`
    and lifecycle control (wait, kill, cleanup).

    Created by :meth:`BwrapSandbox.run_command_streaming`.  The caller MUST call
    :meth:`cleanup` after the process exits (or after calling :meth:`kill`) to
    release temporary resources (e.g. the WSL script file).

    Usage::

        handle = await sandbox.run_command_streaming("ls -la")
        # ... read handle.stdout, handle.stderr incrementally ...
        exit_code = await handle.wait()
        await handle.cleanup()
    """

    __slots__ = ("_process", "_pgid", "_use_wsl", "_script_path", "_sandbox_ref")

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        *,
        pgid: int | None = None,
        use_wsl: bool = False,
    ):
        self._process = process
        self._pgid: int | None = pgid
        self._use_wsl: bool = use_wsl
        self._script_path: str | None = None
        self._sandbox_ref: BwrapSandbox | None = None

    @property
    def stdout(self) -> asyncio.StreamReader | None:
        """stdout stream for incremental reading (4096-byte chunks)."""
        return self._process.stdout

    @property
    def stderr(self) -> asyncio.StreamReader | None:
        """stderr stream for incremental reading (4096-byte chunks)."""
        return self._process.stderr

    @property
    def returncode(self) -> int | None:
        """Process return code (None if still running)."""
        return self._process.returncode

    async def wait(self) -> int:
        """Wait for the command to exit.  Returns the exit code."""
        await self._process.wait()
        return self._process.returncode if self._process.returncode is not None else -1

    async def kill(self) -> None:
        """Kill the running command.

        On native Linux, tries SIGTERM then SIGKILL against the process group
        (bwrap creates a PID namespace but the outer bwrap process itself is
        in the process group created with ``start_new_session=True``).

        On WSL, terminates the wsl.exe wrapper — the inner bwrap processes
        should be cleaned up via ``--die-with-parent`` when the wrapper bash
        receives SIGHUP.

        After calling this, call :meth:`cleanup` to release temporary resources.
        """
        if self._pgid is not None:
            # Native Linux — kill the process group (bwrap + children)
            try:
                os.killpg(self._pgid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        else:
            try:
                self._process.terminate()
            except ProcessLookupError:
                return

        try:
            await asyncio.wait_for(self._process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            # Force kill
            try:
                if self._pgid is not None:
                    try:
                        os.killpg(self._pgid, signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
                else:
                    self._process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass

    async def cleanup(self) -> None:
        """Release temporary resources (script file, etc.).

        Must be called after the process exits — either naturally, via
        :meth:`kill`, or after a timeout.
        """
        if self._script_path is not None and self._sandbox_ref is not None:
            try:
                await self._sandbox_ref._run_linux_command(
                    f"rm -f '{self._script_path}'", timeout=5.0,
                )
            except Exception:
                pass
            self._script_path = None



async def _create_subprocess_exec(*args, **kwargs):
    """Wrapper around asyncio.create_subprocess_exec that suppresses Windows console windows."""
    kwargs.update(_subprocess_kwargs())
    return await asyncio.create_subprocess_exec(*args, **kwargs)


def _shell_quote(s: str) -> str:
    """Shell-escape a string using single quotes.

    Replaces every single quote with `'\''` and wraps the whole thing
    in single quotes.  This is the standard POSIX idiom for embedding
    arbitrary text in a shell command.
    """
    return "'" + s.replace("'", "'\\''") + "'"


def _is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def _subprocess_kwargs():
    """Return kwargs for asyncio.create_subprocess_exec to hide console windows.

    On Windows, ``asyncio.create_subprocess_exec`` creates a console window
    by default for every subprocess.  Passing ``creationflags`` with
    ``CREATE_NO_WINDOW`` suppresses this, preventing the brief black console
    flash (Issue #301).

    Returns:
        dict with ``creationflags`` on Windows; empty dict on other platforms.
    """
    if not _is_windows():
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


class BwrapSandbox:
    """Manages a single bwrap sandbox for one conversation session.

    Automatically detects Windows + WSL and routes all bwrap commands
    through ``wsl.exe -d <distro> -- bash -c "..."`` when needed.
    """

    def __init__(
        self,
        session_key: str,
        workspace: Path | str,
        sandbox_base_dir: Path | str | None = None,
        share_net: bool = False,
        extra_ro_binds: list[str] | None = None,
        extra_rw_binds: list[str] | None = None,
        hostname: str = "miqi-sandbox",
        uid: int = 1000,
        gid: int = 1000,
        wsl_distro: str = "",
        wsl_base_dir: str = "/tmp/miqi-sandboxes",
        sandbox_distro_name: str = "",
        auto_install_deps: bool = True,
    ):
        self.session_key = session_key
        self.workspace = Path(workspace).resolve()
        self.share_net = share_net
        self.extra_ro_binds = extra_ro_binds or []
        self.extra_rw_binds = extra_rw_binds or []
        self.hostname = hostname
        self.uid = uid
        self.gid = gid
        self.wsl_distro = wsl_distro
        self.wsl_base_dir = wsl_base_dir
        self.sandbox_distro_name = sandbox_distro_name
        self.auto_install_deps = auto_install_deps

        # Per-session directories (always Linux-style paths inside WSL or native)
        safe_key = session_key.replace(":", "_").replace("/", "_").replace("\\", "_").replace("'", "_")
        if sandbox_base_dir:
            self._base_dir = Path(sandbox_base_dir) / safe_key
        else:
            self._base_dir = Path(tempfile.gettempdir()) / "miqi-sandboxes" / safe_key

        # When running on Windows, we MUST use Linux paths inside WSL
        if _is_windows():
            self._linux_base_dir = f"{self.wsl_base_dir}/{safe_key}"
        else:
            self._linux_base_dir = str(self._base_dir)

        self.sandbox_home: str = f"{self._linux_base_dir}/home/miqi"
        self.sandbox_workspace: str = f"{self._linux_base_dir}/home/miqi/workspace"
        self.sandbox_rootfs: str = f"{self._linux_base_dir}/rootfs"

        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._bwrap_path: str | None = None
        self._use_wsl: bool = False
        self._detected_distro: str = ""
        self._linux_workspace: str | None = None
        self._log_workspace = Path(workspace).expanduser().resolve()

    # ── WSL detection & command execution ────────────────────────────────

    async def _run_host_command(
        self,
        *args: str,
        timeout: float = 30.0,
    ) -> tuple[int, str, str]:
        """Run a command on the host OS (Windows or Linux).

        On Windows, wraps with ``wsl.exe -d <distro> --`` if needed.
        Returns (exit_code, stdout, stderr).
        """
        if self._use_wsl:
            full_args = self._wsl_prefix() + list(args)
        else:
            full_args = list(args)

        try:
            process = await _create_subprocess_exec(
                *full_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return (-1, "", f"Command timed out after {timeout}s")

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return (process.returncode if process.returncode is not None else -1, stdout, stderr)
        except Exception as exc:
            return (-1, "", f"Failed to run command: {exc}")

    async def _run_linux_command(
        self,
        cmd: str,
        timeout: float = 30.0,
    ) -> tuple[int, str, str]:
        """Run a shell command inside the Linux environment.

        On Windows, runs via ``wsl.exe -d <distro> -- bash -c "..."``.
        On Linux, runs via ``bash -c "..."``.
        """
        if self._use_wsl:
            full_args = self._wsl_prefix() + ["bash", "-c", cmd]
        else:
            full_args = ["bash", "-c", cmd]

        try:
            process = await _create_subprocess_exec(
                *full_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return (-1, "", f"Command timed out after {timeout}s")

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return (process.returncode if process.returncode is not None else -1, stdout, stderr)
        except Exception as exc:
            return (-1, "", f"Failed to run command: {exc}")

    async def _write_wsl_file_via_stdin(
        self,
        linux_path: str,
        content: str,
        timeout: float = 15.0,
    ) -> tuple[int, str, str]:
        """Write content to a file inside WSL by piping through stdin.

        This avoids the Windows CreateProcess command-line length limit
        by passing file content through a pipe rather than as a command
        argument.  The command line stays short:
            wsl.exe -d distro -- bash -c 'cat > /path/to/file'
        while the actual content flows through stdin.
        """
        # Use a short command; data goes through stdin pipe
        write_cmd = f"mkdir -p \"$(dirname '{linux_path}')\" && cat > '{linux_path}'"
        if self._use_wsl:
            full_args = self._wsl_prefix() + ["bash", "-c", write_cmd]
        else:
            full_args = ["bash", "-c", write_cmd]

        try:
            process = await _create_subprocess_exec(
                *full_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(input=content.encode("utf-8")),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return (-1, "", f"Command timed out after {timeout}s")

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return (process.returncode if process.returncode is not None else -1, stdout, stderr)
        except Exception as exc:
            return (-1, "", f"Failed to write file: {exc}")

    def _wsl_prefix(self) -> list[str]:
        """Build the wsl.exe prefix for command execution."""
        distro = self._detected_distro or self.wsl_distro
        if distro:
            return ["wsl.exe", "-d", distro, "--"]
        return ["wsl.exe", "--"]

    @staticmethod
    async def _detect_wsl_distro(preferred: str = "") -> str | None:
        """Detect available WSL distribution with bwrap.

        Returns the distro name if found, None if WSL/bwrap not available.
        """
        if not _is_windows():
            return None

        # Try preferred distro first
        if preferred:
            try:
                proc = await _create_subprocess_exec(
                    "wsl.exe", "-d", preferred, "--", "bash", "-c", "which bwrap",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=15.0)
                if proc.returncode == 0:
                    return preferred
            except Exception:
                pass

        # List all distros and find one with bwrap
        try:
            proc = await _create_subprocess_exec(
                "wsl.exe", "-l", "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_data, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode != 0:
                return None

            output = stdout_data.decode("utf-16-le", errors="replace") if stdout_data else ""
            # WSL -l -q output has null bytes and newlines; clean up
            distros = [
                line.strip().replace("\x00", "")
                for line in output.splitlines()
                if line.strip().replace("\x00", "")
            ]

            for distro in distros:
                if not distro:
                    continue
                try:
                    check = await _create_subprocess_exec(
                        "wsl.exe", "-d", distro, "--", "bash", "-c", "which bwrap",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(check.communicate(), timeout=15.0)
                    if check.returncode == 0:
                        return distro
                except Exception:
                    continue
        except Exception:
            pass

        return None

    @staticmethod
    async def _find_any_wsl_distro(preferred: str = "") -> str | None:
        """Find any available WSL distribution (with or without bwrap).

        Returns the distro name if found, None if no WSL available.
        Skips non-standard distros (docker-desktop*, etc.) by checking
        that bash is available.
        """
        if not _is_windows():
            return None

        async def _distro_has_bash(distro: str) -> bool:
            """Check if a distro has bash (indicating a real Linux distro)."""
            proc = None
            try:
                proc = await _create_subprocess_exec(
                    "wsl.exe", "-d", distro, "--", "bash", "-c", "echo ok",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=30.0)
                return proc.returncode == 0
            except (asyncio.TimeoutError, Exception):
                if proc is not None:
                    proc.kill()
                return False

        # Try preferred distro first
        if preferred:
            if await _distro_has_bash(preferred):
                return preferred

        # List all distros and find the first one with bash
        try:
            proc = await _create_subprocess_exec(
                "wsl.exe", "-l", "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_data, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode != 0:
                return None

            output = stdout_data.decode("utf-16-le", errors="replace") if stdout_data else ""
            distros = [
                line.strip().replace("\x00", "")
                for line in output.splitlines()
                if line.strip().replace("\x00", "")
                and "docker-desktop" not in line.lower()
            ]
            for distro in distros:
                if await _distro_has_bash(distro):
                    return distro
            return None
        except (asyncio.TimeoutError, OSError, ValueError):
            return None
    @staticmethod
    async def _ensure_sandbox_distro(target_name: str = "AIShadowSandbox") -> bool:
        """Create a dedicated sandbox WSL distro if it does not exist.

        Exports the first available non-docker WSL distro to a temporary
        tar file, then imports it as a new distro with the given name.
        This gives the sandbox a root-user distro that can install
        packages without sudo password prompts.

        Returns True if the distro already exists or was created.
        """
        # Check if already exists
        try:
            check = await _create_subprocess_exec(
                "wsl.exe", "-d", target_name, "--", "bash", "-c",
                "echo ok",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(check.communicate(), timeout=10.0)
            if check.returncode == 0:
                logger.info(
                    "Sandbox distro '{}' already exists", target_name,
                )
                return True
        except (asyncio.TimeoutError, OSError):
            pass

        # Find a source distro to export
        source = await BwrapSandbox._find_any_wsl_distro(preferred="")
        if source is None:
            logger.warning("No WSL distro available to create sandbox from")
            return False

        logger.info(
            "Creating sandbox distro '{}' from '{}' (this may take "
            "2-5 minutes)...", target_name, source,
        )

        tar_path = None
        try:
            fd, tar_path = tempfile.mkstemp(
                suffix=".tar", prefix="miqi-sandbox-",
            )
            os.close(fd)

            # Export source distro
            _t0 = time.monotonic()
            export_proc = await _create_subprocess_exec(
                "wsl.exe", "--export", source, tar_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, export_stderr = await asyncio.wait_for(
                export_proc.communicate(), timeout=300.0,
            )
            logger.info("  wsl --export completed in {:.0f}s", time.monotonic() - _t0)
            if export_proc.returncode != 0:
                err = (
                    export_stderr.decode("utf-8", errors="replace")[:200]
                    if export_stderr else "unknown error"
                )
                logger.warning(
                    "Failed to export distro '{}': {}", source, err,
                )
                return False

            # Import as WSL2 sandbox distro in LOCALAPPDATA
            install_dir = str(
                Path(
                    os.environ.get("LOCALAPPDATA", "")
                    or os.environ.get("APPDATA", "")
                    or Path.home() / "AppData" / "Local"
                )
                / "MiQi Sandbox"
            )

            import_proc = await _create_subprocess_exec(
                "wsl.exe", "--import", target_name,
                install_dir, tar_path,
                "--version", "2",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, import_stderr = await asyncio.wait_for(
                import_proc.communicate(), timeout=120.0,
            )
            logger.info("  wsl --import completed in {:.0f}s", time.monotonic() - _t0)
            if import_proc.returncode != 0:
                err = (
                    import_stderr.decode("utf-8", errors="replace")[:200]
                    if import_stderr else "unknown error"
                )
                logger.warning(
                    "Failed to import sandbox distro '{}': {}",
                    target_name, err,
                )
                return False

            # Set default user to root so apt-get never needs a password
            try:
                set_root = await _create_subprocess_exec(
                    "wsl.exe", "-d", target_name, "-u", "root", "--",
                    "bash", "-c",
                    "echo -e '[user]\\ndefault=root' > /etc/wsl.conf",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(
                    set_root.communicate(), timeout=10.0,
                )
                # Terminate so wsl.conf takes effect on next launch
                term = await _create_subprocess_exec(
                    "wsl.exe", "--terminate", target_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(
                    term.communicate(), timeout=10.0,
                )
            except (asyncio.TimeoutError, OSError):
                pass  # best-effort, not fatal

            logger.info(
                "Sandbox distro '{}' created (installed at {})",
                target_name, install_dir,
            )
            return True

        except (asyncio.TimeoutError, OSError) as exc:
            logger.warning(
                "Failed to create sandbox distro '{}': {}",
                target_name, exc,
            )
            return False
        finally:
            if tar_path and os.path.exists(tar_path):
                try:
                    os.remove(tar_path)
                except OSError:
                    pass

    @staticmethod
    async def _ensure_wsl_deps(distro: str) -> bool:
        """Install required packages in a WSL distro and verify bwrap.

        Installs: bubblewrap, coreutils, rsync.

        Returns True if bwrap is available after installation, False otherwise.
        """
        # Quick check: skip if bwrap already installed
        try:
            check = await _create_subprocess_exec(
                "wsl.exe", "-d", distro, "--", "bash", "-c", "which bwrap",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(check.communicate(), timeout=30.0)
            if check.returncode == 0:
                logger.info("bwrap already installed in WSL distro '{}'", distro)
                return True
        except (asyncio.TimeoutError, OSError):
            pass

        # Serialize installation: if another thread is already running
        # apt-get (e.g. sandbox manager background init), poll-wait for
        # bwrap to become available instead of launching a second apt-get.
        # This avoids concurrent apt-get processes racing on dpkg lock.
        if not _install_lock.acquire(blocking=False):
            logger.info(
                "Concurrent apt-get detected in WSL distro '{}' — waiting...",
                distro,
            )
            for i in range(180):
                await asyncio.sleep(1)
                try:
                    recheck = await _create_subprocess_exec(
                        "wsl.exe", "-d", distro, "--", "bash", "-c",
                        "which bwrap",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(recheck.communicate(), timeout=5.0)
                    if recheck.returncode == 0:
                        logger.info(
                            "bwrap installed by concurrent thread in WSL "
                            "distro '{}' after ~{}s", distro, i + 1,
                        )
                        return True
                except (asyncio.TimeoutError, OSError):
                    pass
            logger.warning(
                "Timed out waiting for concurrent apt-get in WSL distro '{}'",
                distro,
            )
            return False

        try:
            _t0 = time.monotonic()
            logger.info(
                "Auto-installing sandbox dependencies in WSL distro '{}'...",
                distro,
            )

            # Determine whether passwordless sudo is available.
            # Default WSL distros have a non-root user + sudo with
            # password — running "sudo apt-get ..." non-interactively
            # would hang waiting for the password prompt until the
            # 180 s timeout.  Check with sudo -n (non-interactive)
            # first and fall back to plain apt-get when sudo needs
            # a password.
            use_sudo = False
            try:
                check_nopass = await _create_subprocess_exec(
                    "wsl.exe", "-d", distro, "--", "bash", "-c",
                    "sudo -n true 2>/dev/null",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(
                    check_nopass.communicate(), timeout=10.0,
                )
                use_sudo = (check_nopass.returncode == 0)
            except (asyncio.TimeoutError, OSError):
                pass

            if use_sudo:
                logger.info("Using passwordless sudo for install in '{}'", distro)
            else:
                logger.info(
                    "sudo needs password in '{}' — trying without sudo",
                    distro,
                )

            # Build install command
            install_cmd = (
                "export DEBIAN_FRONTEND=noninteractive; "
                "apt-get update -qq 2>/dev/null; "
                "apt-get install -y -qq bubblewrap coreutils rsync"
            )
            if use_sudo:
                install_cmd = f"sudo bash -c '{install_cmd}'"

            try:
                proc = await _create_subprocess_exec(
                    "wsl.exe", "-d", distro, "--", "bash", "-c",
                    install_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=180.0,
                )

                if proc.returncode != 0:
                    logger.info(
                        "  apt-get install completed in {:.0f}s (failed)",
                        time.monotonic() - _t0,
                    )
                    err_msg = (
                        stderr.decode("utf-8", errors="replace")[:300]
                        if stderr else "unknown error"
                    )
                    if not use_sudo and (
                        "permission denied" in err_msg.lower()
                        or "are you root" in err_msg.lower()
                    ):
                        err_msg += (
                            " (sudo is required but needs a password. "
                            "Configure passwordless sudo in the WSL distro "
                            "or run: wsl -d {0} -- sudo apt-get install "
                            "bubblewrap coreutils rsync)".format(distro)
                        )
                    logger.warning(
                        "Failed to install dependencies in WSL distro "
                        "'{}': {}", distro, err_msg,
                    )
                    return False
            except (asyncio.TimeoutError, OSError) as exc:
                logger.warning(
                    "Failed to run apt install in WSL distro '{}': {}",
                    distro, exc,
                )
                return False
        finally:
            _install_lock.release()

        # Verify bwrap is now available
        try:
            verify = await _create_subprocess_exec(
                "wsl.exe", "-d", distro, "--", "bash", "-c", "which bwrap",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(verify.communicate(), timeout=30.0)
            if verify.returncode == 0:
                logger.info(
                    "Successfully installed sandbox dependencies in WSL distro "
                    "'{}' (total {:.0f}s)", distro, time.monotonic() - _t0,
                )
                return True
        except (asyncio.TimeoutError, OSError):
            pass

        logger.warning(
            "Dependencies installed but bwrap still not found in WSL distro '{}'",
            distro,
        )
        return False

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Prepare the sandbox filesystem and verify bwrap availability."""
        # Detect execution environment
        if _is_windows():
            self._use_wsl = True
            distro = await self._detect_wsl_distro(self.wsl_distro)
            if not distro and self.auto_install_deps:
                # No distro with bwrap found — try installing deps in any WSL distro
                install_distro = await self._find_any_wsl_distro(self.wsl_distro)
                if install_distro:
                    if await self._ensure_wsl_deps(install_distro):
                        # Retry detection after install
                        distro = await self._detect_wsl_distro(install_distro)
            if not distro:
                raise BwrapSandboxError(
                    "No WSL distribution with bwrap found. "
                    "Install bubblewrap in WSL: apt install bubblewrap"
                )
            self._detected_distro = distro
            self._bwrap_path = "/usr/bin/bwrap"  # Always available if WSL detection passed
            logger.info(
                "Sandbox will run via WSL distro '{}' for session {}",
                distro, self.session_key,
            )
            append_workspace_log(
                self._log_workspace,
                f"Sandbox start via WSL distro={distro} session={self.session_key}",
                level="INFO",
                source="sandbox",
            )
        else:
            self._use_wsl = False
            self._bwrap_path = await self._find_bwrap_native()
            if not self._bwrap_path:
                raise BwrapSandboxError(
                    "bwrap not found. Install it: apt install bubblewrap"
                )

        # Create per-session directory structure inside Linux/WSL
        rc, out, err = await self._run_linux_command(
            f"mkdir -p '{self._linux_base_dir}' '{self.sandbox_home}' '{self.sandbox_workspace}'"
        )
        if rc != 0:
            raise BwrapSandboxError(
                f"Failed to create sandbox directories: {err}"
            )

        # Verify directories actually exist
        rc, _, err = await self._run_linux_command(
            f"test -d '{self.sandbox_home}' && test -d '{self.sandbox_workspace}'"
        )
        if rc != 0:
            raise BwrapSandboxError(
                f"Sandbox directories not found after creation: {err}"
            )

        # Copy workspace into sandbox if it exists
        # For WSL, the workspace path needs to be accessible from inside WSL
        linux_workspace = await self._resolve_workspace_path()
        if linux_workspace:
            # Check if workspace is directly accessible (e.g. /mnt/c/...)
            # In that case, we can skip rsync and just bind-mount it
            rc, _, _ = await self._run_linux_command(f"test -d '{linux_workspace}'")
            if rc == 0:
                logger.debug(
                    "Workspace accessible at {} — will use per-sandbox workspace instead of shared bind-mount",
                    linux_workspace,
                )

        # Always use per-sandbox workspace — no shared host workspace bind mount
        self._linux_workspace = None

        self._running = True
        logger.info(
            "Sandbox prepared for session {}: {}",
            self.session_key,
            self.sandbox_workspace,
        )
        append_workspace_log(
            self._log_workspace,
            f"Sandbox prepared for session={self.session_key} workspace={self.sandbox_workspace}",
            level="INFO",
            source="sandbox",
        )

    async def stop(self) -> None:
        """Stop any running bwrap process and clean up sandbox directories."""
        self._running = False

        # Clean up any streaming handles not manually cleaned up
        for handle in getattr(self, '_streaming_handles', []):
            try:
                await handle.cleanup()
            except Exception:
                pass
        self._streaming_handles = []

        # Kill any running process
        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass
            self._process = None

        # Clean up sandbox filesystem inside Linux/WSL
        rc, _, err = await self._run_linux_command(
            f"rm -rf '{self._linux_base_dir}'"
        )
        if rc == 0:
            logger.info("Sandbox cleaned up: {}", self._linux_base_dir)
            append_workspace_log(
                self._log_workspace,
                f"Sandbox cleaned up session={self.session_key} path={self._linux_base_dir}",
                level="INFO",
                source="sandbox",
            )
        else:
            logger.warning("Failed to clean sandbox {}: {}", self._linux_base_dir, err)
            append_workspace_log(
                self._log_workspace,
                f"Sandbox cleanup failed session={self.session_key} error={err}",
                level="WARNING",
                source="sandbox",
            )

    async def run_command(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> tuple[int, str, str]:
        """Run a command inside the bwrap sandbox.

        Returns:
            (exit_code, stdout, stderr)
        """
        if not self._running or not self._bwrap_path:
            raise BwrapSandboxError("Sandbox not started")

        # ── Defensive: verify sandbox directories still exist ──────────
        # In WSL, tmpfs /tmp directories can vanish between calls (e.g.
        # when multiple sandboxes are created/destroyed in CI).  Recreate
        # if the source bind-mounts are missing so bwrap doesn't fail with
        # "Can't find source path".
        rc, _, _ = await self._run_linux_command(
            f"test -d '{self.sandbox_home}' && test -d '{self.sandbox_workspace}'"
        )
        if rc != 0:
            logger.warning(
                "Sandbox directories missing for {} — recreating ({}, {})",
                self.session_key, self.sandbox_home, self.sandbox_workspace,
            )
            rc2, _, err2 = await self._run_linux_command(
                f"mkdir -p '{self._linux_base_dir}' '{self.sandbox_home}' '{self.sandbox_workspace}'"
            )
            if rc2 != 0:
                raise BwrapSandboxError(
                    f"Sandbox directories vanished and could not be recreated: {err2}"
                )
            logger.info("Sandbox directories recreated for {}", self.session_key)

        bwrap_args = self._build_bwrap_args(command, env=env, cwd=cwd)

        exit_code = -1
        stdout = ""
        stderr = ""

        try:
            if self._use_wsl:
                # Windows CreateProcess has a ~32767 char command-line limit.
                # bwrap with all its --ro-bind-try / --setenv flags can easily
                # exceed that.  Write the full command into a temp shell script
                # inside WSL and execute the script instead — the wsl.exe
                # command line stays short (just "bash /tmp/…").
                exit_code, stdout, stderr = await self._run_bwrap_via_script(bwrap_args, timeout)
            else:
                # Run bwrap natively — no command-line length issue on Linux
                full_args = bwrap_args

                process = await _create_subprocess_exec(
                    *full_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        process.communicate(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
                    exit_code, stdout, stderr = (-1, "", f"Command timed out after {timeout}s")
                else:
                    stdout = stdout_bytes.decode("utf-8", errors="replace")
                    stderr = stderr_bytes.decode("utf-8", errors="replace")
                    exit_code = process.returncode if process.returncode is not None else -1

        except Exception as exc:
            exit_code, stdout, stderr = (-1, "", f"Failed to run bwrap: {exc}")

        # Capture command output to workspace logs for debugging
        self._log_command_result(command, exit_code, stdout, stderr)
        return exit_code, stdout, stderr

    def _log_command_result(
        self, command: str, exit_code: int, stdout: str, stderr: str
    ) -> None:
        """Log the result of a sandbox command to the workspace log file.

        Output is truncated to keep log entries manageable while still
        capturing enough context for debugging.
        """
        cmd_summary = command[:200] + "…" if len(command) > 200 else command
        level = "ERROR" if exit_code != 0 else "INFO"

        append_workspace_log(
            self._log_workspace,
            f"cmd [{self.session_key}] exit={exit_code}: {cmd_summary}",
            level=level,
            source="sandbox",
            session_key=self.session_key,
        )

        stdout_trimmed = stdout.rstrip()
        stderr_trimmed = stderr.rstrip()

        if stdout_trimmed:
            if len(stdout_trimmed) > 5000:
                stdout_trimmed = stdout_trimmed[:5000] + f"\n…[truncated {len(stdout)}B total]"
            append_workspace_log(
                self._log_workspace,
                f"[{self.session_key}] stdout:\n{stdout_trimmed}",
                level="DEBUG",
                source="sandbox",
                session_key=self.session_key,
            )

        if stderr_trimmed:
            if len(stderr_trimmed) > 5000:
                stderr_trimmed = stderr_trimmed[:5000] + f"\n…[truncated {len(stderr)}B total]"
            stderr_level = "WARNING" if exit_code != 0 else "DEBUG"
            append_workspace_log(
                self._log_workspace,
                f"[{self.session_key}] stderr:\n{stderr_trimmed}",
                level=stderr_level,
                source="sandbox",
                session_key=self.session_key,
            )

    async def run_command_streaming(
        self,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> BwrapCommandHandle:
        """Run a command inside the bwrap sandbox with streaming I/O.

        Unlike :meth:`run_command` which buffers all output and returns it
        at once, this method returns a :class:`BwrapCommandHandle` that
        provides incremental stdout/stderr access via
        :class:`asyncio.StreamReader`.  The **caller** is responsible for:

        * reading from ``handle.stdout`` / ``handle.stderr``,
        * calling ``await handle.wait()`` to await the exit code, and
        * calling ``await handle.cleanup()`` to release temporary resources.

        The caller also owns timeout and cancellation — use
        :meth:`BwrapCommandHandle.kill` to stop a running command.

        Returns:
            BwrapCommandHandle with .stdout, .stderr, .wait(), .kill(),
            and .cleanup().

        Raises:
            BwrapSandboxError: if the sandbox is not started.
        """
        if not self._running or not self._bwrap_path:
            raise BwrapSandboxError("Sandbox not started")

        bwrap_args = self._build_bwrap_args(command, env=env, cwd=cwd)

        if not hasattr(self, '_streaming_handles'):
            self._streaming_handles: list[BwrapCommandHandle] = []

        if self._use_wsl:
            handle = await self._run_bwrap_streaming_via_script(bwrap_args)
        else:
            handle = await self._run_bwrap_streaming_native(bwrap_args)

        self._streaming_handles.append(handle)
        # Handles are cleaned up when the sandbox stops (see stop()).
        # No need to wrap cleanup — __slots__ prevents monkey-patching.
        return handle

    async def _run_bwrap_streaming_native(
        self, bwrap_args: list[str],
    ) -> BwrapCommandHandle:
        """Launch bwrap natively with streaming stdout/stderr.

        Uses ``start_new_session=True`` so that :meth:`BwrapCommandHandle.kill`
        can target the entire process group (bwrap + children).
        """
        process = await _create_subprocess_exec(
            *bwrap_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            pgid = os.getpgid(process.pid)
        except (ProcessLookupError, OSError):
            pgid = None

        return BwrapCommandHandle(
            process, pgid=pgid, use_wsl=False,
        )

    async def _run_bwrap_streaming_via_script(
        self, bwrap_args: list[str],
    ) -> BwrapCommandHandle:
        """Launch bwrap via WSL script with streaming stdout/stderr.

        Writes a temp shell script inside WSL (via stdin pipe to avoid the
        32 767-char command-line limit), then executes it with
        ``wsl.exe -d distro -- bash script``.

        The script path is stored on the handle so :meth:`BwrapCommandHandle.cleanup`
        can remove it after the process exits.
        """
        script_id = uuid.uuid4().hex[:12]
        script_path = f"{self._linux_base_dir}/_bwrap_{script_id}.sh"

        escaped_args = " ".join(
            _shell_quote(a) for a in bwrap_args
        )
        script_content = (
            f"#!/bin/bash\n"
            f"# Diagnostic: log whether sandbox dirs needed recreation\n"
            f"for d in '{self.sandbox_home}' '{self.sandbox_workspace}'; do\n"
            f"  if test -d \"$d\"; then\n"
            f"    echo \"[sandbox] dir OK: $d\" >&2\n"
            f"  else\n"
            f"    echo \"[sandbox] dir MISSING — recreating: $d\" >&2\n"
            f"    mkdir -p \"$d\" || {{ echo \"[sandbox] FATAL: cannot create $d\" >&2; exit 1; }}\n"
            f"  fi\n"
            f"done\n"
            f"{escaped_args}\n"
        )

        write_rc, _, write_err = await self._write_wsl_file_via_stdin(
            script_path, script_content,
        )
        if write_rc != 0:
            raise BwrapSandboxError(
                f"Failed to write bwrap streaming script: {write_err}"
            )

        await self._run_linux_command(f"chmod +x '{script_path}'")

        full_args = self._wsl_prefix() + ["bash", script_path]

        process = await _create_subprocess_exec(
            *full_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        handle = BwrapCommandHandle(
            process, pgid=None, use_wsl=True,
        )
        handle._script_path = script_path
        handle._sandbox_ref = self
        return handle

    # ── WSL script-based execution ─────────────────────────────────────

    async def _run_bwrap_via_script(
        self,
        bwrap_args: list[str],
        timeout: float,
    ) -> tuple[int, str, str]:
        """Write bwrap args into a temp shell script inside WSL and execute it.

        This avoids the Windows CreateProcess command-line length limit
        (~32 767 chars) by keeping the wsl.exe invocation short and putting
        the potentially long bwrap command into a file inside the WSL
        filesystem.

        The script content is piped through stdin to avoid the same
        command-line length limit when writing the file.
        """
        # Build a unique script path inside WSL
        script_id = uuid.uuid4().hex[:12]
        script_path = f"{self._linux_base_dir}/_bwrap_{script_id}.sh"

        # Shell-escape each argument for the script
        escaped_args = " ".join(
            _shell_quote(a) for a in bwrap_args
        )
        script_content = (
            f"#!/bin/bash\n"
            f"# Diagnostic: log whether sandbox dirs needed recreation\n"
            f"for d in '{self.sandbox_home}' '{self.sandbox_workspace}'; do\n"
            f"  if test -d \"$d\"; then\n"
            f"    echo \"[sandbox] dir OK: $d\" >&2\n"
            f"  else\n"
            f"    echo \"[sandbox] dir MISSING — recreating: $d\" >&2\n"
            f"    mkdir -p \"$d\" || {{ echo \"[sandbox] FATAL: cannot create $d\" >&2; exit 1; }}\n"
            f"  fi\n"
            f"done\n"
            f"{escaped_args}\n"
        )

        # Write script into WSL via stdin pipe (avoids cmd-line length limit)
        write_rc, _, write_err = await self._write_wsl_file_via_stdin(
            script_path, script_content,
        )
        if write_rc != 0:
            return (-1, "", f"Failed to write bwrap script: {write_err}")

        # Make it executable
        await self._run_linux_command(f"chmod +x '{script_path}'")

        try:
            # Execute the script via wsl.exe — short command line
            full_args = self._wsl_prefix() + ["bash", script_path]

            process = await _create_subprocess_exec(
                *full_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return (-1, "", f"Command timed out after {timeout}s")

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return (process.returncode if process.returncode is not None else -1, stdout, stderr)

        finally:
            # Clean up the script file
            await self._run_linux_command(f"rm -f '{script_path}'", timeout=5.0)

    # ── Bwrap command builder ──────────────────────────────────────────

    # System directories that should be bind-mounted read-only from the host.
    # We bind individual directories instead of `--ro-bind / /` because the
    # latter makes the *entire* root read-only, preventing bwrap from creating
    # mount-point directories (like /home/miqi) for subsequent --bind mounts.
    _RO_BIND_DIRS: list[str] = [
        "/usr", "/bin", "/lib", "/lib64", "/lib32",
        "/etc", "/sbin", "/var", "/opt", "/snap",
    ]

    def _build_bwrap_args(
        self,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> list[str]:
        """Build the full bwrap argument list.

        Returns a list of arguments suitable for ``subprocess.exec`` — no
        shell quoting needed because each argument is passed separately.

        On WSL, this list is directly appended after ``wsl.exe -d distro --``.

        The sandbox layout:
        /usr, /bin, /lib, etc — read-only bind mounts from host
        /tmp                  — tmpfs (writable, per-session)
        /home/miqi            — per-session home (writable bind)
        /home/miqi/workspace  — per-session workspace (writable bind)
        /dev                  — new devtmpfs (minimal)
        /proc                 — new procfs
        """
        args = [self._bwrap_path]

        # ── Namespace isolation ─────────────────────────────────────
        args.append("--unshare-pid")
        if not self.share_net:
            args.append("--unshare-net")
        args.append("--unshare-ipc")
        args.append("--unshare-uts")

        # ── Hostname ────────────────────────────────────────────────
        args.extend(["--hostname", self.hostname])

        # ── UID/GID (requires --unshare-user) ──────────────────────
        args.append("--unshare-user-try")
        args.extend(["--uid", str(self.uid)])
        args.extend(["--gid", str(self.gid)])

        # ── Proc & Dev ──────────────────────────────────────────────
        args.extend(["--proc", "/proc"])
        args.extend(["--dev", "/dev"])

        # ── Read-only host bind mounts ──────────────────────────────
        for d in self._RO_BIND_DIRS:
            args.extend(["--ro-bind-try", d, d])

        # ── /mnt bind mount (needed when running via WSL) ──────────
        # Windows files are accessible via /mnt/c, /mnt/d, etc. in WSL.
        # We need to bind-mount /mnt so the sandbox can access the
        # workspace files that live on the Windows filesystem.
        if self._use_wsl:
            args.extend(["--bind-try", "/mnt", "/mnt"])

        # ── Writable overlays ───────────────────────────────────────
        args.extend(["--tmpfs", "/tmp"])
        args.extend(["--bind", self.sandbox_home, "/home/miqi"])

        # ── Workspace mount ────────────────────────────────────────
        # Always use the per-sandbox workspace directory for full
        # session isolation. Do NOT bind-mount the shared host
        # workspace, which would let any sandbox see all sessions'
        # files (Issue #221).
        args.extend(["--bind", self.sandbox_workspace, "/home/miqi/workspace"])

        # ── /etc/resolv.conf ─────────────────────────────────────────
        # /etc is already ro-bind-mounted from host (share_net=True),
        # which includes the host's resolv.conf. No need to create
        # a separate copy that would fail on read-only /etc.


        # ── Extra bind mounts ───────────────────────────────────────
        for src in self.extra_ro_binds:
            args.extend(["--ro-bind", src, src])
        for src in self.extra_rw_binds:
            args.extend(["--bind", src, src])

        # ── Die with parent ─────────────────────────────────────────
        args.append("--die-with-parent")

        # ── New session ─────────────────────────────────────────────
        args.append("--new-session")

        # ── Environment variables (via --setenv for proper isolation) ──
        sandbox_env = self.get_sandbox_env()
        if env:
            sandbox_env.update(env)
        for k, v in sandbox_env.items():
            args.extend(["--setenv", k, v])

        # ── Command to execute ──────────────────────────────────────
        work_dir = cwd or "/home/miqi/workspace"
        args.extend(["/bin/bash", "-c", f"cd '{work_dir}' && {command}"])

        return args

    # ── Workspace sync ─────────────────────────────────────────────────

    async def _resolve_workspace_path(self) -> str | None:
        """Resolve the workspace path to a Linux-accessible path.

        On Windows, converts Windows paths to WSL paths (e.g.
        C:\\Users\\... → /mnt/c/Users/...) or uses the WSL-native path
        if the workspace is inside WSL's filesystem.
        """
        ws = str(self.workspace)

        if not self._use_wsl:
            # Native Linux — just check it exists
            rc, _, _ = await self._run_linux_command(f"test -d '{ws}'")
            return ws if rc == 0 else None

        # Windows + WSL — check if the workspace is accessible from WSL
        # First, try the path as-is (it might already be a WSL path)
        rc, out, _ = await self._run_linux_command(f"wslpath -u '{ws}' 2>/dev/null")
        if rc == 0 and out.strip():
            linux_path = out.strip()
            # Verify it exists
            rc2, _, _ = await self._run_linux_command(f"test -d '{linux_path}'")
            if rc2 == 0:
                return linux_path

        # Fallback: try common WSL path conversions
        # C:\path → /mnt/c/path
        if len(ws) >= 2 and ws[1] == ":":
            drive = ws[0].lower()
            rest = ws[2:].replace("\\", "/")
            linux_path = f"/mnt/{drive}{rest}"
            rc, _, _ = await self._run_linux_command(f"test -d '{linux_path}'")
            if rc == 0:
                return linux_path

        # Check if workspace is inside WSL filesystem already
        rc, _, _ = await self._run_linux_command(f"test -d '{ws}'")
        if rc == 0:
            return ws

        logger.warning(
            "Workspace path '{}' not accessible from WSL, sandbox will have empty workspace",
            ws,
        )
        return None

    async def _sync_workspace(self, linux_workspace: str) -> None:
        """Copy workspace files into the sandbox's workspace directory.

        Uses rsync if available for efficiency; falls back to cp -r.
        All operations happen inside Linux/WSL.
        """
        try:
            # Try rsync first
            rc, _, _ = await self._run_linux_command(
                f"rsync -a --delete '{linux_workspace}/' '{self.sandbox_workspace}/'",
                timeout=120.0,
            )
            if rc == 0:
                logger.debug("Workspace synced via rsync for {}", self.session_key)
                return
        except Exception:
            pass

        # Fallback: cp -r
        try:
            rc, _, err = await self._run_linux_command(
                f"rm -rf '{self.sandbox_workspace}'/* && "
                f"cp -r '{linux_workspace}/.' '{self.sandbox_workspace}/'",
                timeout=120.0,
            )
            if rc == 0:
                logger.debug("Workspace synced via cp for {}", self.session_key)
            else:
                logger.warning("Failed to sync workspace for {}: {}", self.session_key, err)
        except Exception as exc:
            logger.warning("Failed to sync workspace for {}: {}", self.session_key, exc)

    # ── Utility ────────────────────────────────────────────────────────

    @staticmethod
    async def _find_bwrap_native() -> str | None:
        """Find the bwrap binary on native Linux."""
        for candidate in ("bwrap", "/usr/bin/bwrap", "/usr/local/bin/bwrap"):
            try:
                proc = await _create_subprocess_exec(
                    "which", candidate,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
                if proc.returncode == 0:
                    return candidate
            except FileNotFoundError:
                continue
        return None

    @staticmethod
    async def is_available(wsl_distro: str = "", auto_install_deps: bool = True) -> bool:
        """Check if bwrap is available (natively or via WSL).

        When ``auto_install_deps`` is True and running on Windows, if no
        WSL distro has bwrap installed, this method will:
        1. Auto-create a dedicated sandbox distro (AIShadowSandbox)
           by exporting the first available distro
        2. Install bubblewrap, coreutils, rsync into it
        """
        if _is_windows():
            distro = await BwrapSandbox._detect_wsl_distro(wsl_distro)
            if distro is not None:
                return True
            # No distro with bwrap — try auto-setup
            if auto_install_deps:
                # Ensure a dedicated sandbox distro exists
                target = wsl_distro or "AIShadowSandbox"
                if await BwrapSandbox._ensure_sandbox_distro(target):
                    install_distro = target
                else:
                    install_distro = await BwrapSandbox._find_any_wsl_distro(
                        wsl_distro,
                    )

                if install_distro:
                    cached = _auto_install_cache.get(install_distro)
                    if cached is False:
                        return False  # already tried and failed
                    if await BwrapSandbox._ensure_wsl_deps(install_distro):
                        distro = await BwrapSandbox._detect_wsl_distro(
                            install_distro,
                        )
                        result = distro is not None
                    else:
                        result = False
                    _auto_install_cache[install_distro] = result
                    return result
            return False
        else:
            return await BwrapSandbox._find_bwrap_native() is not None

    @staticmethod
    async def cleanup_dir(linux_dir: str, wsl_distro: str = "") -> None:
        """Remove a sandbox directory from the Linux/WSL filesystem.

        This is used by SandboxManager to clean up stale sandboxes from
        previous bridge runs, without needing a full BwrapSandbox instance.

        Args:
            linux_dir: Absolute path inside Linux/WSL to remove.
            wsl_distro: WSL distribution name (auto-detect if empty).
        """
        if not linux_dir or not linux_dir.startswith("/"):
            logger.warning("Refusing to cleanup non-absolute path: {}", linux_dir)
            return

        # Safety: only allow paths under known sandbox prefixes
        _ALLOWED_PREFIXES = ("/tmp/miqi-sandboxes/", "/tmp/miqi-sandbox")
        if not any(linux_dir.startswith(p) for p in _ALLOWED_PREFIXES):
            logger.warning(
                "Refusing to cleanup path outside allowed prefixes: {}", linux_dir
            )
            return

        if _is_windows():
            # Run via WSL
            distro = wsl_distro
            if not distro:
                distro = await BwrapSandbox._detect_wsl_distro() or ""
            if not distro:
                logger.warning("No WSL distro available for cleanup of {}", linux_dir)
                return
            prefix = ["wsl.exe", "-d", distro, "--"]
        else:
            prefix = []

        try:
            process = await _create_subprocess_exec(
                *prefix, "rm", "-rf", linux_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=15.0
            )
            if process.returncode == 0:
                logger.debug("Cleaned up directory: {}", linux_dir)
            else:
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                logger.warning(
                    "Failed to cleanup {}: {}", linux_dir, stderr.strip()
                )
        except Exception as exc:
            logger.warning("Failed to cleanup {}: {}", linux_dir, exc)

    @property
    def is_running(self) -> bool:
        """True if the sandbox has been started and not stopped."""
        return self._running

    @property
    def workspace_path(self) -> str:
        """The sandbox workspace path visible to tools (Linux-style)."""
        return self.sandbox_workspace

    @property
    def home_path(self) -> str:
        """The sandbox home directory path (Linux-style)."""
        return self.sandbox_home

    def get_sandbox_env(self) -> dict[str, str]:
        """Get environment variables to use inside the sandbox."""
        return {
            "HOME": "/home/miqi",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "en_US.UTF-8",
            "TERM": "xterm-256color",
            "MIQI_SANDBOX": "1",
            "MIQI_SESSION_KEY": self.session_key,
        }
