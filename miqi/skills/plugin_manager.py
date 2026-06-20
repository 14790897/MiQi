"""Plugin discovery and lifecycle management.

Plugins are the top-level packaging format. A plugin can contain:
- Multiple MCP servers (tools)
- Multiple skills (instruction sets)
- Slash commands
- Additional configuration
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from miqi.execution.hook_runtime import (
    HookOutcome,
    HookPoint,
    HookRegistration,
    HookRuntime,
)

# ── shared plugin-name validator ──────────────────────────────────────────

_PLUGIN_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


def validate_plugin_name(name: str) -> None:
    """Validate a plugin name for safe filesystem and registry use.

    Raises ValueError if the name is invalid.
    """
    if not _PLUGIN_NAME_RE.match(name):
        raise ValueError("Invalid plugin manifest name")
    if ".." in name:
        raise ValueError("Invalid plugin manifest name")


@dataclass
class PluginManifest:
    """Manifest file found in a plugin directory (plugin.json)."""
    name: str
    version: str
    description: str
    author: str = ""
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    slash_commands: list[dict[str, str]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    hooks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LoadedPlugin:
    """A successfully loaded and active plugin."""
    manifest: PluginManifest
    path: Path
    scope: str  # "user" | "workspace" | "system"
    status: str = "active"  # "active" | "error" | "disabled"
    error: str | None = None


class PluginManager:
    """Discovers, loads, and manages plugins.

    Plugin search paths (in order):
    1. ~/.miqi/plugins/           — user plugins
    2. <workspace>/.miqi/plugins/ — workspace plugins
    3. <miqi_install>/plugins/    — system/builtin plugins
    """

    def __init__(
        self,
        user_plugins_dir: Path,
        system_plugins_dir: Path,
        workspace: Path | None = None,
        hook_runtime: HookRuntime | None = None,
    ):
        self.user_dir = Path(user_plugins_dir)
        self.system_dir = Path(system_plugins_dir)
        self.workspace = workspace
        self._hook_runtime = hook_runtime
        self._plugins: dict[str, LoadedPlugin] = {}

    def _make_command_callback(self, target: str):
        """Build an async callback that runs ``target`` through a shell."""

        async def _callback(ctx) -> HookOutcome:
            proc = await asyncio.create_subprocess_shell(
                target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode(errors="replace").strip() or "command hook failed"
                return HookOutcome.block(err)
            return HookOutcome.continue_()

        return _callback

    def _make_module_callback(self, plugin_path: Path, target: str):
        """Build an async callback that imports ``pkg.mod:func`` from the plugin path."""
        if ":" not in target:
            raise ValueError(
                f"Module hook target must be 'module.path:func', got: {target}"
            )
        module_path, func_name = target.rsplit(":", 1)

        async def _callback(ctx):
            import sys

            p = str(plugin_path)
            if p not in sys.path:
                sys.path.insert(0, p)
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            result = func(ctx)
            if inspect.isawaitable(result):
                result = await result
            return result

        return _callback

    def _build_hook_registration(
        self,
        source: str,
        plugin_path: Path,
        spec: dict,
    ):
        """Convert a manifest hook spec into a HookRegistration."""
        point = spec["point"].replace("-", "_")
        hook_point = HookPoint[point.upper()]
        tool_pattern = spec.get("match", "*")
        priority = spec.get("priority", 0)
        hook_type = spec["type"]
        target = spec["target"]

        if hook_type == "command":
            callback = self._make_command_callback(target)
        elif hook_type == "module":
            callback = self._make_module_callback(plugin_path, target)
        else:
            raise ValueError(f"Unsupported hook type: {hook_type}")

        return HookRegistration(
            hook_point=hook_point,
            tool_pattern=tool_pattern,
            callback=callback,
            priority=priority,
            source=source,
        )

    def _register_plugin_hooks(self, plugin) -> None:
        """Register all hooks declared by a plugin."""
        if self._hook_runtime is None:
            return
        for spec in plugin.manifest.hooks:
            try:
                reg = self._build_hook_registration(
                    plugin.manifest.name,
                    plugin.path,
                    spec,
                )
            except Exception:
                logger.exception(
                    "Failed to register hook for plugin {}: {}",
                    plugin.manifest.name,
                    spec,
                )
                continue
            self._hook_runtime.register(reg)

    def _unregister_plugin_hooks(self, name: str) -> None:
        """Remove all hook registrations sourced from ``name``."""
        if self._hook_runtime is None:
            return
        self._hook_runtime.unregister_source(name)

    async def discover(self) -> list[LoadedPlugin]:
        """Discover all plugins across all search paths."""
        search_paths = [
            (self.user_dir, "user"),
            (self.system_dir, "system"),
        ]
        if self.workspace:
            search_paths.append(
                (self.workspace / ".miqi" / "plugins", "workspace")
            )

        discovered = []
        for base_dir, scope in search_paths:
            if not base_dir.exists():
                continue
            for plugin_dir in base_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                manifest_path = plugin_dir / "plugin.json"
                if not manifest_path.exists():
                    continue
                try:
                    plugin = await self._load_plugin(
                        plugin_dir, manifest_path, scope
                    )
                    if plugin:
                        self._plugins[plugin.manifest.name] = plugin
                        discovered.append(plugin)
                except Exception as e:
                    logger.error(
                        "Failed to load plugin {}: {}",
                        plugin_dir.name, e,
                    )

        logger.info("Discovered {} plugins", len(discovered))
        return discovered

    async def _load_plugin(
        self,
        plugin_dir: Path,
        manifest_path: Path,
        scope: str,
    ) -> LoadedPlugin | None:
        """Load a single plugin from its directory."""
        import json
        manifest_data = json.loads(manifest_path.read_text())
        manifest = PluginManifest(**manifest_data)
        plugin = LoadedPlugin(
            manifest=manifest, path=plugin_dir, scope=scope
        )
        self._register_plugin_hooks(plugin)
        return plugin

    def get_mcp_servers(self) -> list[dict[str, Any]]:
        """Collect all MCP server configs from active plugins."""
        servers = []
        for plugin in self._plugins.values():
            if plugin.status != "active":
                continue
            for server in plugin.manifest.mcp_servers:
                resolved = dict(server)
                if "cwd" not in resolved:
                    resolved["cwd"] = str(plugin.path)
                servers.append(resolved)
        return servers

    def get_slash_commands(self) -> dict[str, str]:
        """Collect all slash commands from active plugins."""
        commands = {}
        for plugin in self._plugins.values():
            if plugin.status != "active":
                continue
            for cmd in plugin.manifest.slash_commands:
                commands[cmd["name"]] = cmd["description"]
        return commands

    def list_plugins(self) -> list[LoadedPlugin]:
        """List all loaded plugins."""
        return list(self._plugins.values())

    def get_plugin(self, name: str) -> LoadedPlugin | None:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def install_plugin(self, name: str, url: str) -> LoadedPlugin:
        """Install a plugin from a GitHub URL.

        Validates plugin name, clones from URL, discovers the new plugin,
        and returns the loaded plugin. Raises ValueError on invalid input
        or subprocess.CalledProcessError on clone failure.
        """
        import subprocess
        import shutil
        from urllib.parse import urlparse

        # Validate plugin name
        validate_plugin_name(name)

        target_dir = (self.user_dir / name).resolve()
        try:
            target_dir.relative_to(self.user_dir.resolve())
        except ValueError:
            raise ValueError("Invalid plugin path")

        if target_dir.exists():
            raise ValueError(f"Plugin '{name}' already installed")

        # Validate URL
        parsed = urlparse(url)
        ALLOWED_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
        if parsed.scheme != "https":
            raise ValueError("Only HTTPS URLs are supported")
        if parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError(f"Unsupported host: {parsed.hostname}")
        if "@" in parsed.netloc:
            raise ValueError("Credentials in URL are not allowed")

        try:
            subprocess.run(
                ["git", "clone", "--depth=1", "--", url, str(target_dir)],
                check=True, capture_output=True, text=True, timeout=60,
            )
        except subprocess.CalledProcessError as e:
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            raise ValueError(f"Clone failed: {e.stderr}") from e
        except Exception:
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            raise

        # Load the newly-installed plugin synchronously.
        # No background discovery — deterministic and immediate.
        try:
            plugin = self.load_plugin_from_dir(target_dir, "user", expected_name=name)
        except Exception:
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            raise
        return plugin

    def uninstall_plugin(self, name: str) -> bool:
        """Uninstall a plugin by name.

        Removes the plugin directory from user/system dirs and unloads
        the plugin. Returns True if the plugin was found and removed.
        """
        import shutil

        validate_plugin_name(name)

        for base in [self.user_dir, self.system_dir]:
            target = (base / name).resolve()
            try:
                target.relative_to(base.resolve())
            except ValueError:
                continue
            if target.exists():
                self._unregister_plugin_hooks(name)
                shutil.rmtree(target, ignore_errors=True)
                if name in self._plugins:
                    del self._plugins[name]
                return True
        return False

    def discover_sync(self) -> list[LoadedPlugin]:
        """Synchronous discovery used after install/uninstall in AppServer handlers."""
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.discover())

        # In a running event loop, direct sync discovery is unsafe.
        # AppServer async handlers should call discover() themselves.
        raise RuntimeError("discover_sync cannot run inside an active event loop")

    def load_plugin_from_dir(
        self,
        plugin_dir: Path,
        scope: str,
        *,
        expected_name: str | None = None,
    ) -> LoadedPlugin:
        """Load one plugin directory synchronously after install.

        Validates the manifest name and optionally confirms it matches an
        expected name (used by install_plugin to prevent name divergence).
        """
        import json

        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.exists():
            raise ValueError(f"Missing plugin.json in {plugin_dir.name}")
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError(f"Invalid plugin.json in {plugin_dir.name}")
        manifest_name = manifest_data.get("name", "")
        validate_plugin_name(manifest_name)
        if expected_name is not None and manifest_name != expected_name:
            raise ValueError(
                f"Plugin manifest name '{manifest_name}' does not match "
                f"requested name '{expected_name}'"
            )
        manifest = PluginManifest(**manifest_data)
        plugin = LoadedPlugin(manifest=manifest, path=plugin_dir, scope=scope)
        self._plugins[plugin.manifest.name] = plugin
        self._register_plugin_hooks(plugin)
        return plugin

    def toggle_plugin(self, name: str, enabled: bool) -> LoadedPlugin:
        """Toggle a plugin enabled/disabled.

        Raises ValueError if the plugin is not found.
        """

        validate_plugin_name(name)

        plugin = self._plugins.get(name)
        if plugin is None:
            raise ValueError(f"Plugin '{name}' not found")

        if enabled:
            plugin.status = "active"
            self._unregister_plugin_hooks(name)
            self._register_plugin_hooks(plugin)
        else:
            plugin.status = "disabled"
            self._unregister_plugin_hooks(name)
        return plugin
