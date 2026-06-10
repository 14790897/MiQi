"""Sandbox manager — creates/switches/destroys per-session bwrap sandboxes.

Integrates with MiQi's SessionManager to automatically:
1. Create a new sandbox when a session starts
2. Switch sandbox context when the active conversation changes
3. Clean up sandboxes when sessions are archived/deleted

Supports Windows + WSL: automatically detects WSL and routes bwrap
commands through wsl.exe when running on Windows.

State persistence (落盘):
- A JSON state file (sandbox_state.json) tracks all active sandboxes
- On sandbox create/destroy, the file is atomically updated
- On bridge startup, stale sandboxes from previous runs are cleaned up
- On graceful shutdown, all sandboxes are destroyed and state cleared

Usage:
    manager = SandboxManager(workspace=Path("~/.miqi/workspace"))
    await manager.initialize()

    # When a session activates:
    sandbox = await manager.get_or_create("feishu:oc_123")

    # When switching conversations:
    await manager.activate("feishu:oc_123")
    current = manager.active_sandbox  # BwrapSandbox for oc_123

    # When a session is archived/deleted:
    await manager.destroy("feishu:oc_123")
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from miqi.sandbox.bwrap import BwrapSandbox, BwrapSandboxError


class SandboxManager:
    """Manages per-session bwrap sandboxes.

    On Windows, automatically detects WSL and runs bwrap inside WSL.

    State is persisted to disk so that:
    - Crashed/killed bridge instances don't leave orphaned WSL directories
    - On restart, stale sandboxes are automatically cleaned up
    """

    def __init__(
        self,
        workspace: Path,
        sandbox_base_dir: Path | None = None,
        share_net: bool = False,
        enabled: bool = True,
        max_sandboxes: int = 10,
        auto_cleanup: bool = True,
        wsl_distro: str = "",
        wsl_base_dir: str = "/tmp/miqi-sandboxes",
        sandbox_distro_name: str = "AIShadowSandbox",
    ):
        self.workspace = workspace
        self.sandbox_base_dir = sandbox_base_dir or workspace / "sandboxes"
        self.share_net = share_net
        self.enabled = enabled
        self.max_sandboxes = max_sandboxes
        self.auto_cleanup = auto_cleanup
        self.wsl_distro = wsl_distro
        self.wsl_base_dir = wsl_base_dir
        self.sandbox_distro_name = sandbox_distro_name

        self._sandboxes: dict[str, BwrapSandbox] = {}
        self._active_key: str | None = None
        self._lock = asyncio.Lock()
        self._initialized = False

        # ── State persistence ─────────────────────────────────────────
        self._state_file = self._resolve_state_file()

    # ── State file path ───────────────────────────────────────────────

    @staticmethod
    def _resolve_state_file() -> Path:
        """Resolve the state file path next to the config directory."""
        try:
            from miqi.config.loader import get_data_dir
            data_dir = get_data_dir()
        except Exception:
            data_dir = Path.home() / ".miqi"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "sandbox_state.json"

    # ── State persistence ─────────────────────────────────────────────

    def _save_state(self) -> None:
        """Atomically write current sandbox state to disk.

        Each entry records enough information to clean up the sandbox
        directory even without an in-memory BwrapSandbox instance.
        """
        entries = []
        for key, sandbox in self._sandboxes.items():
            entries.append({
                "session_key": key,
                "wsl_base_dir": sandbox.wsl_base_dir,
                "linux_base_dir": sandbox._linux_base_dir,
                "sandbox_home": sandbox.sandbox_home,
                "sandbox_workspace": sandbox.sandbox_workspace,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "sandboxes": entries,
        }

        try:
            # Atomic write: write to temp file, then rename
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._state_file.parent),
                prefix=".sandbox_state_",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                # On Windows, need to remove target first before rename
                if self._state_file.exists():
                    self._state_file.unlink()
                os.rename(tmp_path, str(self._state_file))
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.debug("Sandbox state saved: {} entries", len(entries))
        except Exception as exc:
            logger.warning("Failed to save sandbox state: {}", exc)

    def _load_state(self) -> dict[str, Any] | None:
        """Read the persisted sandbox state from disk.

        Returns the parsed JSON payload, or None if no valid state file exists.
        """
        if not self._state_file.exists():
            return None
        try:
            with open(self._state_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read sandbox state: {}", exc)
            return None

    async def cleanup_stale(self) -> int:
        """Clean up sandbox directories left from a previous bridge run.

        Called on bridge startup. Reads the state file, removes all listed
        sandbox directories in WSL/Linux, and clears the state file.

        Returns the number of stale sandboxes cleaned up.
        """
        state = self._load_state()
        if state is None:
            return 0

        entries = state.get("sandboxes", [])
        if not entries:
            # Empty state file — nothing to clean
            self._clear_state_file()
            return 0

        cleaned = 0
        for entry in entries:
            linux_base_dir = entry.get("linux_base_dir")
            if not linux_base_dir:
                continue

            # Use BwrapSandbox's static cleanup helper
            try:
                await BwrapSandbox.cleanup_dir(
                    linux_base_dir,
                    wsl_distro=self.wsl_distro,
                )
                cleaned += 1
                logger.info(
                    "Cleaned up stale sandbox: {} ({})",
                    entry.get("session_key", "?"), linux_base_dir,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to clean stale sandbox {}: {}",
                    entry.get("session_key", "?"), exc,
                )

        # Clear the state file — all listed sandboxes have been handled
        self._clear_state_file()
        logger.info("Stale sandbox cleanup complete: {} removed", cleaned)
        return cleaned

    def _clear_state_file(self) -> None:
        """Remove or truncate the state file."""
        try:
            if self._state_file.exists():
                self._state_file.unlink()
        except OSError as exc:
            logger.warning("Failed to clear sandbox state file: {}", exc)

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        """Check if bwrap is available and initialize the manager.

        Also cleans up any stale sandboxes from a previous bridge run.

        Returns True if sandboxing is available, False otherwise.
        """
        if self._initialized:
            # Already initialized, check current state
            return self._lock is not None

        if not self.enabled:
            logger.info("Sandbox disabled by configuration")
            self._initialized = True
            return False

        available = await BwrapSandbox.is_available(wsl_distro=self.wsl_distro)
        if not available:
            logger.warning(
                "bwrap not found — sandbox isolation is NOT available. "
                "Install bubblewrap: apt install bubblewrap"
            )
            self._initialized = True
            return False

        # Only create lock if not already created (handles re-initialization)
        if self._lock is None:
            self._lock = asyncio.Lock()
        
        self._initialized = True

        # Clean up sandboxes left from a previous bridge run
        stale_count = await self.cleanup_stale()
        if stale_count > 0:
            logger.info(
                "Cleaned up {} stale sandbox(es) from previous run",
                stale_count,
            )

        logger.info("Sandbox manager initialized (bwrap available)")
        return True

    # ── Sandbox CRUD ───────────────────────────────────────────────────

    async def get_or_create(self, session_key: str) -> BwrapSandbox | None:
        """Get an existing sandbox for the session, or create a new one.

        Returns None if sandboxing is not available or disabled.
        """
        if not self.enabled or not self._initialized:
            return None

        # Check bwrap availability on first create
        if not await BwrapSandbox.is_available(wsl_distro=self.wsl_distro):
            return None

        if self._lock is None:
            logger.error("Sandbox manager lock not initialized")
            return None

        async with self._lock:
            if session_key in self._sandboxes:
                sandbox = self._sandboxes[session_key]
                if sandbox.is_running:
                    return sandbox
                # Sandbox was stopped, remove and recreate
                del self._sandboxes[session_key]

            # Enforce max sandboxes limit
            if len(self._sandboxes) >= self.max_sandboxes:
                await self._evict_oldest()

            sandbox = BwrapSandbox(
                session_key=session_key,
                workspace=self.workspace,
                sandbox_base_dir=self.sandbox_base_dir if not self.wsl_distro else None,
                share_net=self.share_net,
                wsl_distro=self.wsl_distro,
                wsl_base_dir=self.wsl_base_dir,
                sandbox_distro_name=self.sandbox_distro_name,
            )

            try:
                await sandbox.start()
                self._sandboxes[session_key] = sandbox
                self._save_state()
                logger.info("Created sandbox for session: {}", session_key)
                return sandbox
            except BwrapSandboxError as exc:
                logger.error("Failed to create sandbox for {}: {}", session_key, exc)
                return None

    async def activate(self, session_key: str) -> BwrapSandbox | None:
        """Set the active sandbox for the given session.

        This is called when the user switches to a different conversation.
        Returns the activated sandbox, or None if not available.
        """
        sandbox = await self.get_or_create(session_key)
        self._active_key = session_key
        return sandbox

    async def destroy(self, session_key: str) -> bool:
        """Stop and remove a sandbox for the given session."""
        sandbox = None
        if self._lock is not None:
            try:
                async with self._lock:
                    sandbox = self._sandboxes.pop(session_key, None)
            except RuntimeError:
                sandbox = self._sandboxes.pop(session_key, None)
        else:
            sandbox = self._sandboxes.pop(session_key, None)

        if sandbox is None:
            return False

        await sandbox.stop()
        self._save_state()

        if self._active_key == session_key:
            self._active_key = None

        logger.info("Destroyed sandbox for session: {}", session_key)
        return True

    async def destroy_all(self) -> int:
        """Stop and remove all sandboxes. Returns count destroyed."""
        count = 0
        sandboxes = []
        
        if self._lock is not None:
            try:
                async with self._lock:
                    sandboxes = list(self._sandboxes.items())
                    self._sandboxes.clear()
                    self._active_key = None
            except RuntimeError:
                sandboxes = list(self._sandboxes.items())
                self._sandboxes.clear()
                self._active_key = None
        else:
            sandboxes = list(self._sandboxes.items())
            self._sandboxes.clear()
            self._active_key = None

        for key, sandbox in sandboxes:
            await sandbox.stop()
            count += 1
        
        # Save empty state after destroying all
        self._save_state()
        return count

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def active_sandbox(self) -> BwrapSandbox | None:
        """Get the currently active sandbox."""
        if self._active_key and self._active_key in self._sandboxes:
            return self._sandboxes[self._active_key]
        return None

    @property
    def active_key(self) -> str | None:
        return self._active_key

    @property
    def sandbox_count(self) -> int:
        return len(self._sandboxes)

    def get_sandbox(self, session_key: str) -> BwrapSandbox | None:
        """Get a sandbox by session key without creating one."""
        return self._sandboxes.get(session_key)

    def list_sandboxes(self) -> list[dict[str, Any]]:
        """List all active sandboxes with their status."""
        result = []
        for key, sandbox in self._sandboxes.items():
            result.append({
                "session_key": key,
                "is_active": key == self._active_key,
                "is_running": sandbox.is_running,
                "workspace": sandbox.workspace_path,
            })
        return result

    # ── Internal ───────────────────────────────────────────────────────

    async def _evict_oldest(self) -> None:
        """Evict the oldest (FIFO - first in, first out) sandbox."""
        if not self._sandboxes:
            return
        # FIFO: evict the first key that isn't active
        for key in list(self._sandboxes.keys()):
            if key != self._active_key:
                sandbox = self._sandboxes.pop(key)
                await sandbox.stop()
                self._save_state()
                logger.info("Evicted sandbox for session: {}", key)
                return
        # All are active? Evict the first one anyway
        key = next(iter(self._sandboxes))
        sandbox = self._sandboxes.pop(key)
        await sandbox.stop()
        self._save_state()
        if self._active_key == key:
            self._active_key = None
        logger.info("Force-evicted sandbox for session: {}", key)
