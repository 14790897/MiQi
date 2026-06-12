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
    exit_code, stdout, stderr = await sandbox.run_command("ls -la")
    await sandbox.stop()
"""

import asyncio
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

# Windows: hide child process console window
_SUBPROCESS_KWARGS: dict = {}
if platform.system() == "Windows":
    _SUBPROCESS_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW


def _win_hide() -> dict:
    """Return kwargs to hide console window on Windows."""
    return _SUBPROCESS_KWARGS


class BwrapSandboxError(Exception):
    """Error raised when bwrap operations fail."""


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

        # Per-session directories (always Linux-style paths inside WSL or native)
        safe_key = session_key.replace(":", "_").replace("/", "_").replace("\\", "_")
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
        self.sandbox_etc: str = f"{self._linux_base_dir}/etc"  # writable /etc copy

        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._bwrap_path: str | None = None
        self._use_wsl: bool = False
        self._detected_distro: str = ""
        self._linux_workspace: str | None = None

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
            process = await asyncio.create_subprocess_exec(
                *full_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            **_win_hide(),
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
            process = await asyncio.create_subprocess_exec(
                *full_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            **_win_hide(),
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
        write_cmd = f"cat > '{linux_path}'"
        if self._use_wsl:
            full_args = self._wsl_prefix() + ["bash", "-c", write_cmd]
        else:
            full_args = ["bash", "-c", write_cmd]

        try:
            process = await asyncio.create_subprocess_exec(
                *full_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            **_win_hide(),
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
        # If a dedicated sandbox distro is configured, always use it
        # This avoids sudo requirement because sandbox uses --unshare-user-try
        if self.sandbox_distro_name:
            return ["wsl.exe", "-d", self.sandbox_distro_name, "--"]
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
                proc = await asyncio.create_subprocess_exec(
                    "wsl.exe", "-d", preferred, "--", "bash", "-c", "which bwrap",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                **_win_hide(),
                )
                await proc.communicate()
                if proc.returncode == 0:
                    return preferred
            except Exception:
                pass

        # List all distros and find one with bwrap
        try:
            proc = await asyncio.create_subprocess_exec(
                "wsl.exe", "-l", "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            **_win_hide(),
            )
            stdout_data, _ = await proc.communicate()
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
                    check = await asyncio.create_subprocess_exec(
                        "wsl.exe", "-d", distro, "--", "bash", "-c", "which bwrap",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    **_win_hide(),
                    )
                    await check.communicate()
                    if check.returncode == 0:
                        return distro
                except Exception:
                    continue
        except Exception:
            pass

        return None

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Prepare the sandbox filesystem and verify bwrap availability."""
        # Detect execution environment
        if _is_windows():
            self._use_wsl = True
            distro = await self._detect_wsl_distro(self.wsl_distro)
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
        else:
            self._use_wsl = False
            self._bwrap_path = await self._find_bwrap_native()
            if not self._bwrap_path:
                raise BwrapSandboxError(
                    "bwrap not found. Install it: apt install bubblewrap"
                )

        # Create per-session directory structure inside Linux/WSL
        rc, out, err = await self._run_linux_command(
            f"mkdir -p '{self.sandbox_home}' '{self.sandbox_workspace}'"
        )
        if rc != 0:
            raise BwrapSandboxError(
                f"Failed to create sandbox directories: {err}"
            )

        # Copy workspace into sandbox if it exists
        # For WSL, the workspace path needs to be accessible from inside WSL
        linux_workspace = await self._resolve_workspace_path()
        if linux_workspace:
            # Check if workspace is directly accessible (e.g. /mnt/c/...)
            # In that case, we can skip rsync and just bind-mount it
            rc, _, _ = await self._run_linux_command(f"test -d '{linux_workspace}'")
            if rc == 0:
                # Store for potential bind-mount in bwrap args
                self._linux_workspace = linux_workspace
                # Skip sync — the workspace will be bind-mounted read-only
                # and the sandbox gets its own writable copy via /home/miqi/workspace
                logger.debug(
                    "Workspace accessible at {} — will bind-mount instead of rsync",
                    linux_workspace,
                )
            else:
                self._linux_workspace = None
        else:
            self._linux_workspace = None

        # ── Copy host /etc into a writable sandbox-local copy ───────
        # bwrap's --ro-bind-try /etc /etc can silently fail in WSL (the
        # source directory may not be bind-mountable).  Instead, copy the
        # entire /etc into the sandbox base directory and bind-mount that
        # copy.  This also lets us inject custom resolv.conf / nsswitch.conf
        # without dealing with read-only overlay ordering.
        rc, _, err = await self._run_linux_command(
            f"cp -a /etc/. '{self.sandbox_etc}/' 2>/dev/null || mkdir -p '{self.sandbox_etc}'"
        )
        if rc != 0:
            logger.warning("Failed to copy /etc: {}", err)
            # Fallback: create empty /etc and populate only essentials
            await self._run_linux_command(f"mkdir -p '{self.sandbox_etc}'")

        # Inject DNS configuration into the sandbox /etc copy
        rc, _, err = await self._run_linux_command(
            f"cp /etc/resolv.conf '{self.sandbox_etc}/resolv.conf' 2>/dev/null || "
            f"echo 'nameserver 8.8.8.8' > '{self.sandbox_etc}/resolv.conf'; "
            f"echo 'nameserver 114.114.114.114' >> '{self.sandbox_etc}/resolv.conf'"
        )
        if rc != 0:
            logger.warning("Failed to create resolv.conf: {}", err)

        rc, _, err = await self._run_linux_command(
            f"cp /etc/nsswitch.conf '{self.sandbox_etc}/nsswitch.conf' 2>/dev/null || "
            f"printf 'hosts: files dns\n' > '{self.sandbox_etc}/nsswitch.conf'"
        )
        if rc != 0:
            logger.warning("Failed to create nsswitch.conf: {}", err)

        self._running = True
        logger.info(
            "Sandbox prepared for session {}: {}",
            self.session_key,
            self.sandbox_workspace,
        )

    async def stop(self) -> None:
        """Stop any running bwrap process and clean up sandbox directories."""
        self._running = False

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
        else:
            logger.warning("Failed to clean sandbox {}: {}", self._linux_base_dir, err)

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

        bwrap_args = self._build_bwrap_args(command, env=env, cwd=cwd)

        try:
            if self._use_wsl:
                # Windows CreateProcess has a ~32767 char command-line limit.
                # bwrap with all its --ro-bind-try / --setenv flags can easily
                # exceed that.  Write the full command into a temp shell script
                # inside WSL and execute the script instead — the wsl.exe
                # command line stays short (just "bash /tmp/…").
                return await self._run_bwrap_via_script(bwrap_args, timeout)
            else:
                # Run bwrap natively — no command-line length issue on Linux
                full_args = bwrap_args

                process = await asyncio.create_subprocess_exec(
                    *full_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                **_win_hide(),
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
            return (-1, "", f"Failed to run bwrap: {exc}")

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
        script_content = f"#!/bin/bash\n{escaped_args}\n"

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

            process = await asyncio.create_subprocess_exec(
                *full_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            **_win_hide(),
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
        "/sbin", "/var", "/opt", "/snap",
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
        # If we have a Linux workspace path accessible from WSL,
        # bind-mount it directly as the sandbox workspace.
        # Otherwise, use the per-session directory (which may have
        # been synced via rsync on native Linux).
        if self._linux_workspace:
            args.extend(["--bind", self._linux_workspace, "/home/miqi/workspace"])
        else:
            args.extend(["--bind", self.sandbox_workspace, "/home/miqi/workspace"])

        # ── /etc — writable copy from sandbox base dir ─────────────
        # We copy the host's /etc during start() and inject custom DNS
        # files.  Binding the entire copy avoids the ro-bind-try /etc /etc
        # silent-failure problem in WSL and gives us full control.
        args.extend(["--bind", self.sandbox_etc, "/etc"])

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
                proc = await asyncio.create_subprocess_exec(
                    "which", candidate,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                **_win_hide(),
                )
                await proc.wait()
                if proc.returncode == 0:
                    return candidate
            except FileNotFoundError:
                continue
        return None

    @staticmethod
    async def is_available(wsl_distro: str = "") -> bool:
        """Check if bwrap is available (natively or via WSL)."""
        if _is_windows():
            distro = await BwrapSandbox._detect_wsl_distro(wsl_distro)
            return distro is not None
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
            process = await asyncio.create_subprocess_exec(
                *prefix, "rm", "-rf", linux_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            **_win_hide(),
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
