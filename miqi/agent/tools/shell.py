"""Shell execution tool with bwrap sandbox support."""

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from miqi.agent.tools.base import Tool


class ExecTool(Tool):
    """Tool to execute shell commands, optionally inside a bwrap sandbox."""

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        env_passthrough: list[str] | None = None,
        approval_callback=None,
        sandbox_manager=None,
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.env_passthrough: frozenset[str] = frozenset(env_passthrough or [])
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",              # del /f, del /q
            r"\brmdir\s+/s\b",               # rmdir /s
            r"(?:^|[;&|]\s*)format\b",       # format (as standalone command only)
            r"\b(mkfs|diskpart)\b",          # disk operations
            r"\bdd\s+if=",                   # dd
            r">\s*/dev/sd",                  # write to disk
            r"\b(shutdown|reboot|poweroff)\b",  # system power
            r":\(\)\s*\{.*\};\s*:",          # fork bomb
            r"\bsudo\b",                     # privilege escalation
            r"\beval\b",                     # code/string evaluation
            r"\bsource\b",                   # source external scripts
            r"`[^`\n]{1,500}`",              # backtick command substitution
            r"\$\([^)\n]{1,500}\)",          # $() command substitution
            r"\|\s*(ba|da|z|fi|c)?sh\b",    # pipe to any shell variant
            r"\b(?:curl|wget)\b[^;\n]{0,200}\|\s*python[23]?\b",  # download-and-execute via Python
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
        self.approval_callback = approval_callback
        self._sandbox_manager = sandbox_manager

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                }
            },
            "required": ["command"]
        }

    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()

        # If desktop approval callback is wired in, use the full approval system.
        # Otherwise fall back to the static guard.
        if self.approval_callback is not None:
            import functools
            from miqi.agent.command_approval import check_dangerous_command
            loop = asyncio.get_event_loop()
            check_fn = functools.partial(
                check_dangerous_command,
                command,
                approval_callback=self.approval_callback,
            )
            approval_result = await loop.run_in_executor(None, check_fn)
            if not approval_result.get("approved", True):
                return approval_result.get(
                    "message",
                    "Error: Command blocked — user denied approval.",
                )
        else:
            guard_error = self._guard_command(command, cwd)
            if guard_error:
                return guard_error

        # Try sandbox execution first if a sandbox manager is available
        if self._sandbox_manager is not None:
            sandbox = self._sandbox_manager.active_sandbox
            if sandbox and sandbox.is_running:
                return await self._execute_in_sandbox(sandbox, command, cwd)

        # Fall back to direct execution (no sandbox)
        return await self._execute_direct(command, cwd)

    async def _execute_in_sandbox(
        self, sandbox, command: str, cwd: str
    ) -> str:
        """Execute a command inside the bwrap sandbox."""
        try:
            # Build sandbox-relative working directory
            sandbox_cwd = self._resolve_sandbox_cwd(cwd)

            # Use only the sandbox's built-in environment variables.
            # Do NOT merge the host's os.environ into the sandbox — the
            # sandbox is an isolated Linux environment and does not need
            # (or want) Windows host env vars like PATH, TEMP, PROGRAMFILES
            # etc.  Passing all those via --setenv bloats the bwrap command
            # line far beyond Windows' 32 767-char limit.
            sandbox_env = sandbox.get_sandbox_env()

            # Only pass through explicitly allowed env vars from the host
            if self.env_passthrough:
                safe_env = self._build_safe_env()
                for k in self.env_passthrough:
                    if k in safe_env and k not in sandbox_env:
                        sandbox_env[k] = safe_env[k]

            exit_code, stdout, stderr = await sandbox.run_command(
                command,
                timeout=self.timeout,
                env=sandbox_env,
                cwd=sandbox_cwd,
            )

            output_parts = []
            if stdout:
                output_parts.append(stdout)
            if stderr and stderr.strip():
                output_parts.append(f"STDERR:\n{stderr}")
            if exit_code != 0:
                output_parts.append(f"\nExit code: {exit_code}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            # Truncate very long output
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"

            return result

        except Exception as e:
            logger.error("Sandbox execution failed: {} — {}", type(e).__name__, e)
            # Do NOT silently fall back to host execution.
            # The model needs to know the sandbox failed so it can adjust
            # its commands (e.g. use Linux paths instead of Windows paths).
            return (
                f"Error: Sandbox execution failed — {type(e).__name__}: {e}\n"
                f"Hint: You are running inside a Linux sandbox. Use Linux-style "
                f"paths (e.g. /home/miqi/workspace/) and Linux commands."
            )

    def _resolve_sandbox_cwd(self, cwd: str) -> str:
        """Map a working directory to its sandbox equivalent.

        Rules:
        - /home/miqi/workspace/... → already a sandbox path, use as-is
        - /mnt/c/...              → already a WSL path, remap to /home/miqi/workspace/...
        - C:\\Users\\...           → Windows path, remap relative to workspace
        - Relative path            → resolve against /home/miqi/workspace
        """
        import re

        # Already a sandbox path
        if cwd.startswith("/home/miqi/"):
            return cwd

        # WSL /mnt/ path — remap to sandbox workspace
        mnt_match = re.match(r"^/mnt/([a-z])/(.+)$", cwd)
        if mnt_match:
            drive = mnt_match.group(1)
            rest = mnt_match.group(2)
            # If workspace matches, compute relative
            if self.working_dir:
                ws_str = str(self.working_dir).replace("\\", "/")
                ws_match = re.match(r"^([A-Za-z]):/(.+)$", ws_str)
                if ws_match and ws_match.group(1).lower() == drive:
                    ws_rest = ws_match.group(2).rstrip("/")
                    if rest.startswith(ws_rest + "/") or rest == ws_rest:
                        rel = rest[len(ws_rest):].lstrip("/")
                        return f"/home/miqi/workspace/{rel}" if rel else "/home/miqi/workspace"
            return cwd  # Can't map, use as-is (may fail but at least visible)

        # Windows absolute path
        win_match = re.match(r"^([A-Za-z]):[/\\](.+)$", cwd)
        if win_match and self.working_dir:
            try:
                rel = Path(cwd).relative_to(self.working_dir)
                return f"/home/miqi/workspace/{rel}"
            except ValueError:
                pass
            # Fallback: compute from drive letter
            drive = win_match.group(1).lower()
            rest = win_match.group(2).replace("\\", "/")
            ws_str = str(self.working_dir).replace("\\", "/")
            ws_match = re.match(r"^([A-Za-z]):/(.+)$", ws_str)
            if ws_match and ws_match.group(1).lower() == drive:
                ws_rest = ws_match.group(2).rstrip("/")
                if rest.startswith(ws_rest + "/") or rest == ws_rest:
                    rel = rest[len(ws_rest):].lstrip("/")
                    return f"/home/miqi/workspace/{rel}" if rel else "/home/miqi/workspace"
            # Not under workspace — map as /mnt/c/...
            return f"/mnt/{drive}/{rest}"

        # Relative path or other — default to workspace root
        return "/home/miqi/workspace"

    async def _execute_direct(self, command: str, cwd: str) -> str:
        """Execute a command directly on the host (no sandbox)."""
        try:
            _kwargs: dict = {}
            if os.name == "nt":
                _kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=self._build_safe_env(),
                **_kwargs,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                # Wait for the process to fully terminate so pipes are
                # drained and file descriptors are released.
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return f"Error: Command timed out after {self.timeout} seconds"

            output_parts = []

            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            # Truncate very long output
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"

            return result

        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _build_safe_env(self) -> dict[str, str]:
        """Return a sanitised copy of os.environ with credential variables removed.

        MCP servers inject secrets (API keys, tokens, passwords) into the
        process environment.  Without this filter, any shell subprocess spawned
        by the agent would inherit those secrets, leaking them to executed
        commands (e.g. ``exec("env")``).

        Variables listed in ``self.env_passthrough`` are explicitly exempted
        from the filter.  This lets operators selectively allow scripts run via
        the exec tool to access specific credentials (e.g. ``OPENAI_API_KEY``)
        without opening the door to every secret in the environment.

        Note: this filter does NOT apply to MCP server processes — those are
        started by the MCP SDK (StdioServerParameters) and always inherit the
        parent environment unchanged.
        """
        _sensitive = re.compile(
            r"(api[_-]?key|secret|token|password|passwd)", re.IGNORECASE
        )
        _sensitive_prefixes = (
            "OPENAI_", "ANTHROPIC_", "FEISHU_", "DINGTALK_",
            "TELEGRAM_", "SLACK_", "DISCORD_", "QQ_", "GROQ_",
            "AZURE_", "AWS_", "GOOGLE_", "GITHUB_", "BRAVE_", "OLLAMA_",
        )
        return {
            k: v for k, v in os.environ.items()
            if k in self.env_passthrough
            or (not _sensitive.search(k) and not k.startswith(_sensitive_prefixes))
        }

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Best-effort safety guard for potentially destructive commands."""
        cmd = command.strip()
        lower = cmd.lower()

        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()

            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            # Only match absolute paths — avoid false positives on relative
            # paths like ".venv/bin/python" where "/bin/python" would be
            # incorrectly extracted by the old pattern.
            posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)

            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None
