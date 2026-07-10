"""Shell execution tool with bwrap sandbox support."""

import asyncio
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from miqi.agent.tools.base import Tool
from miqi.execution.sandbox_policy import SandboxType
from miqi.protocol.events import (
    ExecCommandBeginEvent,
    ExecCommandEndEvent,
    ExecCommandOutputDeltaEvent,
)
from miqi.protocol.permissions import NetworkSandboxPolicy

# ── Internal result carrier ────────────────────────────────────────────


@dataclass
class _ExecResult:
    """Carries the output of a single command execution plus metadata
    needed to emit an accurate ExecCommandEndEvent."""

    output: str
    exit_code: int = 0
    duration_ms: int = 0
    cancelled: bool = False
    timed_out: bool = False
    sandbox_type: str = "none"


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
            r"\brm\s+-[rf]{1,2}\b",  # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",  # del /f, del /q
            r"\brmdir\s+/s\b",  # rmdir /s
            r"(?:^|[;&|]\s*)format\b",  # format (as standalone command only)
            r"\b(mkfs|diskpart)\b",  # disk operations
            r"\bdd\s+if=",  # dd
            r">\s*/dev/sd",  # write to disk
            r"\b(shutdown|reboot|poweroff)\b",  # system power
            r":\(\)\s*\{.*\};\s*:",  # fork bomb
            r"\bsudo\b",  # privilege escalation
            r"\beval\b",  # code/string evaluation
            r"\bsource\b",  # source external scripts
            r"`[^`\n]{1,500}`",  # backtick command substitution
            r"\$\([^)\n]{1,500}\)",  # $() command substitution
            r"\|\s*(ba|da|z|fi|c)?sh\b",  # pipe to any shell variant
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
                "command": {"type": "string", "description": "The shell command to execute"},
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()

        # Phase 21: extract runtime-injected event emitter and metadata
        event_emitter = kwargs.pop("_event_emitter", None)
        turn_id = kwargs.pop("_turn_id", "")
        tool_call_id = kwargs.pop("_tool_call_id", "")
        cancel_event = kwargs.pop("_cancel_event", None)

        # Phase 42: extract exec source tag (shell vs userShell)
        exec_source = kwargs.pop("_exec_source", "shell")

        # Phase 31.8: consume ledger runtime and thread_id injected by
        # ToolOrchestrator for replay-persistent event recording.
        ledger_runtime = kwargs.pop("_ledger_runtime", None)
        thread_id = kwargs.pop("_thread_id", "")

        # Phase 31: consume SandboxSelection injected by ToolOrchestrator.
        _sandbox = kwargs.pop("_sandbox", None)
        _session_key = kwargs.pop("_session_key", None)

        # Resolve sandbox_type for the begin event from the actual selection
        if _sandbox is not None:
            sandbox_type = _sandbox.sandbox_type.value
        elif self._sandbox_manager is not None:
            sandbox_type = "bwrap"
        else:
            sandbox_type = "none"

        # Phase 21: emit exec begin event
        if event_emitter is not None:
            await event_emitter.emit(
                ExecCommandBeginEvent(
                    turn_id=turn_id,
                    tool_call_id=tool_call_id,
                    command=command,
                    cwd=cwd,
                    sandbox_type=sandbox_type,
                    source=exec_source,
                )
            )

        # Phase 31.8: record exec start in ledger for replay
        if ledger_runtime is not None:
            await ledger_runtime.append_item(
                thread_id=thread_id,
                turn_id=turn_id,
                item_type="exec_started",
                payload={
                    "tool_call_id": tool_call_id,
                    "command": command,
                    "cwd": cwd,
                    "sandbox_type": sandbox_type,
                    "source": exec_source,
                },
            )

        # Phase 31.5: exec end event needs a single exit point.
        # _ExecResult carries output + metadata so the end event is accurate.
        async def _run() -> _ExecResult:
            # If desktop approval callback is wired in, use the full
            # approval system.  Otherwise fall back to the static guard.
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
                    msg = approval_result.get(
                        "message",
                        "Error: Command blocked — user denied approval.",
                    )
                    return _ExecResult(output=msg, exit_code=1)
            else:
                guard_error = self._guard_command(command, cwd)
                if guard_error:
                    return _ExecResult(output=guard_error, exit_code=1)

            # Phase 31.6: if cancel_event is already set before we start,
            # return immediately without spawning a subprocess.
            if cancel_event is not None and cancel_event.is_set():
                return _ExecResult(
                    output="Error: Command cancelled before start.",
                    exit_code=-1, cancelled=True,
                )

            # ── common args shared by every execution path ──────────
            exec_kwargs = dict(
                event_emitter=event_emitter,
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                cancel_event=cancel_event,
                # Phase 31.8: ledger runtime and thread_id for replay
                ledger_runtime=ledger_runtime,
                thread_id=thread_id,
                # Session key for per-session sandbox isolation
                session_key=_session_key,
            )

            # Phase 31: if ToolOrchestrator injected a SandboxSelection,
            # it is the single source of truth for how this command runs.
            # ExecTool MUST follow it — no independent sandbox decision.
            if _sandbox is not None:
                return await self._execute_with_sandbox_selection(
                    _sandbox, command, cwd, **exec_kwargs,
                )

            # Legacy path (no orchestrator): session_key required for isolation
            if self._sandbox_manager is not None and _session_key:
                sandbox = await self._sandbox_manager.get_or_create(_session_key)
                if sandbox and sandbox.is_running:
                    return await self._execute_in_sandbox(
                        sandbox, command, cwd, **exec_kwargs,
                    )

            # Fall back to direct execution (no sandbox)
            return await self._execute_direct(command, cwd, **exec_kwargs)

        exec_result = await _run()

        # Phase 31.5: emit exec end event with real metadata.
        if event_emitter is not None:
            await event_emitter.emit(ExecCommandEndEvent(
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                exit_code=exec_result.exit_code,
                duration_ms=exec_result.duration_ms,
                output_size=len(exec_result.output),
            ))

        # Phase 31.8: record exec completion in ledger for replay,
        # including terminal status flags (timeout, cancel, non-zero exit).
        if ledger_runtime is not None:
            await ledger_runtime.append_item(
                thread_id=thread_id,
                turn_id=turn_id,
                item_type="exec_completed",
                payload={
                    "tool_call_id": tool_call_id,
                    "exit_code": exec_result.exit_code,
                    "duration_ms": exec_result.duration_ms,
                    "output_size": len(exec_result.output),
                    "cancelled": exec_result.cancelled,
                    "timed_out": exec_result.timed_out,
                },
            )

        return exec_result.output

    async def _execute_in_sandbox(
        self, sandbox, command: str, cwd: str,
        *,
        timeout_ms: int | None = None,
        env_passthrough: list[str] | None = None,
        event_emitter=None,
        turn_id: str = "",
        tool_call_id: str = "",
        cancel_event: asyncio.Event | None = None,
        # Phase 31.8: ledger runtime for replay-persistent event recording
        ledger_runtime=None,
        thread_id: str = "",
        session_key: str | None = None,
    ) -> _ExecResult:
        """Execute a command inside the bwrap sandbox with streaming I/O.

        Phase 33.2: Uses ``sandbox.run_command_streaming()`` for incremental
        stdout/stderr, emits :class:`ExecCommandOutputDeltaEvent`, and
        supports ``cancel_event`` and timeout with process-group kill.

        Follows the same internal task pattern as :meth:`_execute_direct`
        (proc_wait, cancel_wait, stdout_task, stderr_task) so cancel/timeout
        behaviour is consistent across sandboxed and direct execution paths.
        """
        effective_timeout = (timeout_ms / 1000) if timeout_ms else self.timeout
        effective_env_passthrough: frozenset[str]
        if env_passthrough is not None:
            effective_env_passthrough = frozenset(env_passthrough)
        else:
            effective_env_passthrough = self.env_passthrough

        # Phase 31.6: honour cancel_event before starting sandbox work.
        if cancel_event is not None and cancel_event.is_set():
            return _ExecResult(
                output="Error: Command cancelled before sandbox start.",
                exit_code=-1, cancelled=True,
            )

        start = time.monotonic()

        # Build sandbox env and cwd
        sandbox_cwd = self._resolve_sandbox_cwd(cwd)
        sandbox_env = sandbox.get_sandbox_env()
        if effective_env_passthrough:
            safe_env = self._build_safe_env(extra_passthrough=list(effective_env_passthrough))
            for k in effective_env_passthrough:
                if k in safe_env and k not in sandbox_env:
                    sandbox_env[k] = safe_env[k]

        # Phase 33.2: use streaming API for incremental I/O + cancel support
        try:
            handle = await sandbox.run_command_streaming(
                command, env=sandbox_env, cwd=sandbox_cwd,
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error("Sandbox execution failed: {} — {}", type(e).__name__, e)
            return _ExecResult(
                output=(
                    f"Error: Sandbox execution failed — {type(e).__name__}: {e}\n"
                    f"Hint: You are running inside a Linux sandbox. Use Linux-style "
                    f"paths (e.g. /home/miqi/workspace/) and Linux commands."
                ),
                exit_code=1,
                duration_ms=duration_ms,
            )

        # ── Launch all internal tasks (same pattern as _execute_direct) ──
        stdout_task: asyncio.Task = asyncio.create_task(
            self._read_stream(
                handle.stdout, "stdout",
                event_emitter=event_emitter,
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                ledger_runtime=ledger_runtime,
                thread_id=thread_id,
            ),
        )
        stderr_task: asyncio.Task = asyncio.create_task(
            self._read_stream(
                handle.stderr, "stderr",
                event_emitter=event_emitter,
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                ledger_runtime=ledger_runtime,
                thread_id=thread_id,
            ),
        )
        proc_wait: asyncio.Task = asyncio.create_task(handle.wait())
        cancel_wait: asyncio.Task | None = None
        stdout_text = ""
        stdout_trunc = False
        stderr_text = ""
        stderr_trunc = False

        cancelled = False
        timed_out = False

        try:
            if cancel_event is not None:
                cancel_wait = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait(
                    [proc_wait, cancel_wait],
                    timeout=effective_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancel_wait in done:
                    cancelled = True
                elif not done:
                    timed_out = True

                # ── Normal completion: cancel_wait was *not* set — clean up ──
                if cancel_wait is not None and not cancel_wait.done():
                    cancel_wait.cancel()
                    try:
                        await cancel_wait
                    except asyncio.CancelledError:
                        pass
            else:
                try:
                    await asyncio.wait_for(proc_wait, timeout=effective_timeout)
                except asyncio.TimeoutError:
                    timed_out = True

            # ── Cancel / timeout: kill process group, then await proc_wait ──
            if cancelled or timed_out:
                await handle.kill()
                if not proc_wait.done():
                    try:
                        await proc_wait
                    except Exception:
                        pass

            # ── Wait for stream readers — they see EOF when pipes close ──
            stdout_text, stdout_trunc = await stdout_task
            stderr_text, stderr_trunc = await stderr_task

        finally:
            # ── Safety net — NO task survives this method ────────────
            for task in (cancel_wait, proc_wait, stdout_task, stderr_task):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

            # ── Release sandbox temporary resources (WSL script file) ───────
            try:
                await handle.cleanup()
            except Exception:
                pass

        duration_ms = int((time.monotonic() - start) * 1000)
        exit_code = handle.returncode if handle.returncode is not None else -1

        # ── Build result text ─────────────────────────────────────────
        if cancelled:
            return _ExecResult(
                output="Error: Command cancelled by user.",
                exit_code=exit_code, duration_ms=duration_ms,
                cancelled=True,
            )
        if timed_out:
            return _ExecResult(
                output=(
                    f"Error: Command timed out after "
                    f"{effective_timeout:.0f} seconds"
                ),
                exit_code=exit_code, duration_ms=duration_ms,
                timed_out=True,
            )

        trunc_note = ""
        if stdout_trunc or stderr_trunc:
            trunc_note = "\n[output truncated]"

        output_parts: list[str] = []
        if stdout_text:
            output_parts.append(stdout_text)
        if stderr_text and stderr_text.strip():
            output_parts.append(f"STDERR:\n{stderr_text}")
        if exit_code != 0:
            output_parts.append(f"\nExit code: {exit_code}")
        if trunc_note:
            output_parts.append(trunc_note)

        result = "\n".join(output_parts) if output_parts else "(no output)"

        # Truncate aggregated result at a readable limit
        max_len = 10_000
        if len(result) > max_len:
            result = result[:max_len] + (
                f"\n... (truncated, {len(result) - max_len} more chars)"
            )

        return _ExecResult(
            output=result, exit_code=exit_code, duration_ms=duration_ms,
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

    async def _execute_with_sandbox_selection(
        self, selection: Any, command: str, cwd: str,
        *,
        event_emitter=None,
        turn_id: str = "",
        tool_call_id: str = "",
        cancel_event: asyncio.Event | None = None,
        ledger_runtime=None,
        thread_id: str = "",
        session_key: str | None = None,
    ) -> _ExecResult:
        """Execute a command according to the ToolOrchestrator's SandboxSelection.

        This is the SINGLE enforcement point for sandbox policy.  The
        ``selection`` object is the output of
        ``SandboxPolicyEngine.select()`` and was injected by
        ``ToolOrchestrator._execute_in_sandbox()``.  ExecTool MUST NOT
        second-guess it or silently fall back to a weaker execution mode.

        Rules (Phase 31):
        - NONE       → direct host execution (orchestrator explicitly allowed it).
        - BWRAP      → must use bwrap sandbox.  Unavailable → fail closed.
        - LANDLOCK   → unsupported yet.  Fail closed.
        - RESTRICTED → direct execution with cwd/env/timeout enforcement.
        """
        st = selection.sandbox_type
        common = dict(
            timeout_ms=selection.timeout_ms,
            env_passthrough=list(selection.env_passthrough),
            event_emitter=event_emitter,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            cancel_event=cancel_event,
            # Phase 31.8: pass ledger runtime and thread_id to sub-executors
            ledger_runtime=ledger_runtime,
            thread_id=thread_id,
        )

        # ── NONE: orchestrator explicitly allowed direct execution ──────
        if st == SandboxType.NONE:
            return await self._execute_direct(command, cwd, **common)

        # ── BWRAP: strongest isolation; session_key preferred ──────────
        if st == SandboxType.BWRAP:
            if self._sandbox_manager is None:
                return _ExecResult(
                    output="Error: BWRAP sandbox required but sandbox manager is unavailable.",
                    exit_code=-1, sandbox_type="bwrap",
                )
            # Prefer session_key for per-session isolation, fall back to active sandbox
            if session_key:
                sandbox = await self._sandbox_manager.get_or_create(session_key)
            else:
                sandbox = self._sandbox_manager.active_sandbox
            if sandbox is not None and sandbox.is_running:
                return await self._execute_in_sandbox(
                    sandbox, command, cwd, **common,
                )
            # FAIL CLOSED — do NOT silently run on the host.
            return _ExecResult(
                output=(
                    "Error: BWRAP sandbox is required by policy but no sandbox "
                    "is currently active.  The command was NOT executed on the "
                    "host.  Check that the sandbox is running and retry."
                ),
                exit_code=1,
            )

        # ── LANDLOCK: not yet implemented ───────────────────────────────
        if st == SandboxType.LANDLOCK:
            return _ExecResult(
                output=(
                    "Error: LANDLOCK sandbox is not yet implemented in MiQi. "
                    "The command was NOT executed."
                ),
                exit_code=1,
            )

        # ── RESTRICTED: process-level restrictions ──────────────────────
        if st == SandboxType.RESTRICTED:
            return await self._execute_restricted(
                command, cwd, sandbox_selection=selection, **common,
            )

        return _ExecResult(
            output=f"Error: Unknown sandbox type '{st}'",
            exit_code=1,
        )

    async def _execute_restricted(
        self, command: str, cwd: str, sandbox_selection: Any,
        *,
        timeout_ms: int | None = None,
        env_passthrough: list[str] | None = None,
        event_emitter=None,
        turn_id: str = "",
        tool_call_id: str = "",
        cancel_event: asyncio.Event | None = None,
        # Phase 31.8: ledger runtime for replay-persistent event recording
        ledger_runtime=None,
        thread_id: str = "",
    ) -> _ExecResult:
        """Execute with RESTRICTED sandbox policy enforcement.

        Phase 33.3 hardened enforcement:
        - cwd MUST be within workspace (always, not config-gated)
        - Command is scanned for file paths outside workspace
        - Network policy: BLOCK_ALL → fail closed (cannot enforce
          network isolation in direct host execution)
        - timeout_ms and env_passthrough from SandboxSelection
        """
        # 1. Resolve workspace — required for RESTRICTED enforcement.
        if not self.working_dir:
            return _ExecResult(
                output=(
                    "Error: RESTRICTED sandbox requires a workspace but "
                    "none is configured.  Command was NOT executed."
                ),
                exit_code=1,
            )
        workspace = Path(self.working_dir).resolve()

        # 2. cwd MUST be within workspace — always enforced for
        #    RESTRICTED, regardless of restrict_to_workspace config.
        try:
            Path(cwd).resolve().relative_to(workspace)
        except ValueError:
            return _ExecResult(
                output=(
                    f"Error: RESTRICTED sandbox policy requires cwd to "
                    f"be within the workspace.  cwd={cwd} is outside "
                    f"workspace={workspace}.  Command was NOT executed."
                ),
                exit_code=1,
            )

        # 3. Scan command for file paths that reference locations
        #    outside the workspace.  Conservative static scan — may
        #    reject commands with path-like string literals.  The
        #    model can adjust its command to use workspace paths.
        unsafe = self._find_paths_outside_workspace(command, cwd, workspace)
        if unsafe:
            return _ExecResult(
                output=(
                    f"Error: RESTRICTED sandbox policy: command "
                    f"references paths outside workspace: "
                    f"{', '.join(unsafe[:5])}.  Command was NOT "
                    f"executed."
                ),
                exit_code=1,
            )

        # 4. Network policy — BLOCK_ALL means we must fail closed.
        #    Direct host execution cannot enforce network isolation.
        if sandbox_selection.network_policy == NetworkSandboxPolicy.BLOCK_ALL:
            return _ExecResult(
                output=(
                    "Error: RESTRICTED sandbox cannot enforce network "
                    "isolation in direct host execution.  Set "
                    "network_allowed=True in the permission profile to "
                    "allow network access under RESTRICTED, or use "
                    "BWRAP sandbox for full isolation.  Command was "
                    "NOT executed."
                ),
                exit_code=1,
            )

        # 5. Proceed with direct host execution — timeout and
        #    env_passthrough from SandboxSelection.
        return await self._execute_direct(
            command, cwd,
            timeout_ms=sandbox_selection.timeout_ms,
            env_passthrough=list(sandbox_selection.env_passthrough),
            event_emitter=event_emitter,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            cancel_event=cancel_event,
            ledger_runtime=ledger_runtime,
            thread_id=thread_id,
        )

    # ── Path scanning (Phase 33.3 RESTRICTED enforcement) ─────────────

    @staticmethod
    def _find_paths_outside_workspace(
        command: str, cwd: str, workspace: Path,
    ) -> list[str]:
        """Find file paths in *command* that resolve outside *workspace*.

        Conservative static scan — does NOT parse shell syntax.
        Detects:
        - Windows absolute paths (C:\\..., D:\\...)
        - POSIX absolute paths (/etc/..., /tmp/..., /mnt/c/...)
        - Explicit traversal patterns (../, ..\\)
        - Redirect targets (> path, >> path, < path)
        - Shell variable expansion ($VAR, ${VAR}) — always unsafe
        - Tilde expansion (~/path, ~user/path) — expanded then checked

        Paths that appear inside string literals (e.g.
        ``python -c "open('/etc/passwd')"``) ARE detected — this is a
        real file access, even if wrapped in code.

        Returns a list of unsafe path strings (empty if all safe).
        """
        cwd_path = Path(cwd).resolve()
        ws = workspace.resolve()
        candidates: set[str] = set()

        # ── 1. Windows absolute paths: C:\\..., D:\\..., etc. ──────
        for m in re.finditer(
            r'\b([A-Za-z]:[\\/][^\s\"\'|&;<>`$()[\]]*)', command,
        ):
            candidates.add(m.group(1).rstrip('.,;:'))

        # ── 2. POSIX absolute paths (/usr/..., /etc/..., /mnt/...) ─
        #    Exclude paths after :// (URLs).
        for m in re.finditer(
            r'(?<!:/)(/[^\s\"\'|&;<>`$()[\]]{2,})', command,
        ):
            candidates.add(m.group(1).rstrip('.,;:'))

        # ── 3. Explicit traversal: ../file or ..\\file ─────────────
        for m in re.finditer(
            r'\.\.[\\/][^\s\"\'|&;<>`$()[\]]*', command,
        ):
            candidates.add(m.group(0).rstrip('.,;:'))

        # ── 4. Redirect targets: > path, >> path, 2> path, < path ─
        for m in re.finditer(
            r'[12]?[><]+\s*([^\s|&;<>]+)', command,
        ):
            target = m.group(1).strip('\'"')
            if target:
                candidates.add(target)

        # ── 5. Shell variable expansion: $VAR/path, ${VAR}/path ────
        #    Statically unresolvable — always treated as unsafe when
        #    followed by a path separator (indicating file access).
        for m in re.finditer(
            r'\$[a-zA-Z_][a-zA-Z0-9_]*(?:/[^\s\"\'|&;<>`$()[\]]+)?',
            command,
        ):
            candidates.add(m.group(0).rstrip('.,;:'))
        for m in re.finditer(
            r'\$\{[a-zA-Z_][a-zA-Z0-9_]*\}(?:/[^\s\"\'|&;<>`$()[\]]+)?',
            command,
        ):
            candidates.add(m.group(0).rstrip('.,;:'))

        # ── 6. Tilde expansion: ~/path, ~user/path ─────────────────
        for m in re.finditer(
            r'~[a-zA-Z0-9_-]*(?:/[^\s\"\'|&;<>`$()[\]]+)?', command,
        ):
            candidates.add(m.group(0).rstrip('.,;:'))

        # ── Resolve and check each candidate ───────────────────────
        unsafe: list[str] = []
        for path_str in sorted(candidates):
            # Skip empty, pure whitespace, or shell operators
            if not path_str or not path_str.strip():
                continue
            if path_str in ('|', '||', '&&', '&', ';', '2>', '1>'):
                continue
            try:
                # Phase 33.3-REVIEW: expand tilde (~/path, ~user/path)
                # before resolving.  Shell variable references ($VAR,
                # ${VAR}) are NEVER expanded — their runtime value is
                # unknowable statically, so they are always unsafe.
                expanded = path_str
                if path_str.startswith('~'):
                    expanded = os.path.expanduser(path_str)
                    # If expanduser returned the original unchanged,
                    # the tilde couldn't be resolved → unsafe.
                    if expanded == path_str:
                        unsafe.append(path_str)
                        continue

                # Reject any path containing an unresolved $ — shell
                # variable expansion is unknowable statically.
                if '$' in expanded:
                    unsafe.append(path_str)
                    continue

                p = Path(expanded)
                if not p.is_absolute():
                    p = cwd_path / expanded
                resolved = p.resolve()
                try:
                    resolved.relative_to(ws)
                except ValueError:
                    unsafe.append(path_str)
            except (ValueError, OSError):
                # Can't resolve — conservative: treat as unsafe.
                unsafe.append(path_str)

        return unsafe

    # ── Streaming helpers ────────────────────────────────────────────

    @staticmethod
    async def _read_stream(
        stream: asyncio.StreamReader | None,
        stream_name: str,
        *,
        event_emitter,
        turn_id: str,
        tool_call_id: str,
        max_chars: int = 50_000,
        # Phase 31.8: ledger runtime for replay-persistent delta recording
        ledger_runtime=None,
        thread_id: str = "",
    ) -> tuple[str, bool]:
        """Read *stream* incrementally, emit delta events, accumulate text.

        Returns ``(accumulated_text, was_truncated)``.
        """
        if stream is None:
            return "", False

        chunks: list[str] = []
        total = 0
        truncated = False
        while True:
            try:
                chunk = await stream.read(4096)
            except Exception:
                break
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            remaining = max_chars - total
            if remaining <= 0:
                truncated = True
                break
            if len(text) > remaining:
                text = text[:remaining]
                truncated = True
            chunks.append(text)
            total += len(text)
            if event_emitter is not None:
                await event_emitter.emit(ExecCommandOutputDeltaEvent(
                    turn_id=turn_id,
                    tool_call_id=tool_call_id,
                    stream=stream_name,
                    delta=text,
                ))
            # Phase 31.8: record exec output delta in ledger for replay
            if ledger_runtime is not None:
                await ledger_runtime.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="exec_output_delta",
                    content=text,
                    payload={
                        "tool_call_id": tool_call_id,
                        "stream": stream_name,
                    },
                )
            if truncated:
                break
        return "".join(chunks), truncated

    async def _kill_process(self, process: asyncio.subprocess.Process) -> None:
        """Terminate, then kill *process* gracefully to avoid orphans."""
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass

    # ── Direct execution (Phase 31.5 streaming + 31.6 cancel/timeout) ──

    async def _execute_direct(
        self, command: str, cwd: str,
        *,
        timeout_ms: int | None = None,
        env_passthrough: list[str] | None = None,
        event_emitter=None,
        turn_id: str = "",
        tool_call_id: str = "",
        cancel_event: asyncio.Event | None = None,
        # Phase 31.8: ledger runtime for replay-persistent exec event recording
        ledger_runtime=None,
        thread_id: str = "",
        session_key: str | None = None,
    ) -> _ExecResult:
        """Execute a command directly on the host (no sandbox).

        Phase 31.5: stdout/stderr are read incrementally and each chunk
        is emitted as an ``ExecCommandOutputDeltaEvent``.  The final text
        is still accumulated for the tool result.

        Phase 31.6: *cancel_event* is raced against process completion.
        On cancel or timeout the subprocess is terminate-d then kill-ed.
        ``duration_ms`` measures real wall-clock time.

        Phase 31.6+ (resource cleanup): Every internal asyncio.Task
        (proc_wait, cancel_wait, stdout_task, stderr_task) is guaranteed
        to be completed — via natural completion, explicit await after
        kill, or cancel+await — before this method returns.  The finally
        block is a safety net that cancels and awaits any task that
        wasn't handled by the primary paths.
        """
        effective_timeout = (timeout_ms / 1000) if timeout_ms else self.timeout
        start = time.monotonic()

        try:
            _kwargs: dict = {}
            if os.name == "nt":
                _kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=self._build_safe_env(extra_passthrough=env_passthrough),
                **_kwargs,
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return _ExecResult(
                output=f"Error executing command: {str(e)}",
                exit_code=1,
                duration_ms=duration_ms,
            )

        # ── Launch all internal tasks ─────────────────────────────────
        stdout_task: asyncio.Task = asyncio.create_task(
            self._read_stream(
                process.stdout, "stdout",
                event_emitter=event_emitter,
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                ledger_runtime=ledger_runtime,
                thread_id=thread_id,
            ),
        )
        stderr_task: asyncio.Task = asyncio.create_task(
            self._read_stream(
                process.stderr, "stderr",
                event_emitter=event_emitter,
                turn_id=turn_id,
                tool_call_id=tool_call_id,
                ledger_runtime=ledger_runtime,
                thread_id=thread_id,
            ),
        )
        proc_wait: asyncio.Task = asyncio.create_task(process.wait())
        cancel_wait: asyncio.Task | None = None
        stdout_text = ""
        stdout_trunc = False
        stderr_text = ""
        stderr_trunc = False

        cancelled = False
        timed_out = False

        try:
            if cancel_event is not None:
                cancel_wait = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait(
                    [proc_wait, cancel_wait],
                    timeout=effective_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancel_wait in done:
                    cancelled = True
                elif not done:
                    timed_out = True

                # ── Normal completion: cancel_wait was *not* set — clean up ──
                if cancel_wait is not None and not cancel_wait.done():
                    cancel_wait.cancel()
                    try:
                        await cancel_wait
                    except asyncio.CancelledError:
                        pass
            else:
                try:
                    await asyncio.wait_for(proc_wait, timeout=effective_timeout)
                except asyncio.TimeoutError:
                    timed_out = True

            # ── Cancel / timeout: kill process, then await proc_wait ──
            if cancelled or timed_out:
                await self._kill_process(process)
                # After kill the process has exited — proc_wait should be
                # done (or nearly done).  Explicitly await to guarantee
                # no pending task remains.
                if not proc_wait.done():
                    try:
                        await proc_wait
                    except Exception:
                        pass

            # ── Wait for stream readers — they see EOF when pipes close ──
            # Normal path: readers complete naturally.
            # Cancel/timeout path: after process is dead, pipes close and
            # readers see EOF (or are cancelled in the safety net below).
            stdout_text, stdout_trunc = await stdout_task
            stderr_text, stderr_trunc = await stderr_task

        finally:
            # ── Safety net — NO task survives this method ────────────
            for task in (cancel_wait, proc_wait, stdout_task, stderr_task):
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

        duration_ms = int((time.monotonic() - start) * 1000)
        exit_code = process.returncode if process.returncode is not None else -1

        # ── Build result text ─────────────────────────────────────────
        if cancelled:
            return _ExecResult(
                output="Error: Command cancelled by user.",
                exit_code=exit_code, duration_ms=duration_ms,
                cancelled=True,
            )
        if timed_out:
            return _ExecResult(
                output=(
                    f"Error: Command timed out after "
                    f"{effective_timeout:.0f} seconds"
                ),
                exit_code=exit_code, duration_ms=duration_ms,
                timed_out=True,
            )

        trunc_note = ""
        if stdout_trunc or stderr_trunc:
            trunc_note = "\n[output truncated]"

        output_parts: list[str] = []
        if stdout_text:
            output_parts.append(stdout_text)
        if stderr_text and stderr_text.strip():
            output_parts.append(f"STDERR:\n{stderr_text}")
        if exit_code != 0:
            output_parts.append(f"\nExit code: {exit_code}")
        if trunc_note:
            output_parts.append(trunc_note)

        result = "\n".join(output_parts) if output_parts else "(no output)"

        # Truncate aggregated result at a readable limit
        max_len = 10_000
        if len(result) > max_len:
            result = result[:max_len] + (
                f"\n... (truncated, {len(result) - max_len} more chars)"
            )

        return _ExecResult(
            output=result, exit_code=exit_code, duration_ms=duration_ms,
        )

    def _build_safe_env(
        self, *, extra_passthrough: list[str] | None = None,
    ) -> dict[str, str]:
        """Return a sanitised copy of os.environ with credential variables removed.

        MCP servers inject secrets (API keys, tokens, passwords) into the
        process environment.  Without this filter, any shell subprocess spawned
        by the agent would inherit those secrets, leaking them to executed
        commands (e.g. ``exec("env")``).

        Variables listed in ``self.env_passthrough`` (and optionally
        ``extra_passthrough`` from a SandboxSelection) are explicitly exempted
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
        passthrough = set(self.env_passthrough)
        if extra_passthrough:
            passthrough.update(extra_passthrough)
        return {
            k: v for k, v in os.environ.items()
            if k in passthrough
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
