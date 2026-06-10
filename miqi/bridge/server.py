"""
MiQi bridge server — stdin/stdout JSON-line protocol.

Protocol:
  Request:  {"id": "<uuid>", "method": "<name>", "params": {...}}
  Response: {"id": "<uuid>", "result": {...}}
  Error:    {"id": "<uuid>", "error": "<message>"}
  Event:    {"id": "<uuid>", "type": "<event_type>", "data": {...}}

Events (type field) are sent during chat for streaming progress:
  - "progress": tool-call hint or progress milestone
  - "final": chat complete with full response content
  - "error": chat encountered an error

All JSON is written to stdout one line per message. Logs go to stderr.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
import signal
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

# Force UTF-8 on Windows (default is GBK/cp936 which cannot encode emoji)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')

# Get raw binary stdout for _send so we bypass any remaining text-layer encoding
_stdout_buffer = sys.stdout.buffer if hasattr(sys.stdout, 'buffer') else None

_stdout_lock = threading.Lock()


def _log(msg: str, level: str = "INFO") -> None:
    """Unified log function — writes to stderr with [miqi-bridge] prefix.

    Also routes through loguru so that all loguru-based modules (sandbox,
    agent loop, etc.) appear in the same stream.
    """
    print(f"[miqi-bridge] {msg}", file=sys.stderr, flush=True)


def _init_logging() -> None:
    """Configure loguru to output alongside the bridge's _log() format.

    Replaces loguru's default handler with one that uses the [miqi-bridge]
    prefix and writes to stderr, so all module-level logger.info/error calls
    are visible in the same terminal stream.
    """
    from loguru import logger

    # Remove the default handler (sink #0) which uses loguru's verbose format
    logger.remove()

    # Add a clean handler that matches _log()'s style
    logger.add(
        sys.stderr,
        format="<level>[miqi-bridge] {name}:{function}:{line} | {message}</level>",
        level="INFO",
        colorize=True,
    )


def _send(data: dict[str, Any]) -> None:
    """Write one atomic JSON line to stdout as UTF-8 bytes (thread-safe)."""
    line = (json.dumps(data, ensure_ascii=False) + "\n").encode('utf-8')
    with _stdout_lock:
        if _stdout_buffer is not None:
            _stdout_buffer.write(line)
            _stdout_buffer.flush()
        else:
            sys.stdout.write(line.decode('utf-8'))
            sys.stdout.flush()


def _result(req_id: str, result: Any = None) -> None:
    _send({"id": req_id, "result": result if result is not None else {}})


def _error(req_id: str, message: str) -> None:
    _send({"id": req_id, "error": message})


def _event(req_id: str, event_type: str, data: Any) -> None:
    _send({"id": req_id, "type": event_type, "data": data})


def _terminal_event(req_id: str, event_type: str, data: Any) -> bool:
    """Send a terminal event (final/error/aborted) for req_id.

    Returns True if this is the first terminal event for this request.
    Returns False (and drops the event) if a terminal event was already sent
    — this prevents duplicate terminal states from racing abort vs completion.
    """
    if not _state.mark_terminated(req_id):
        _log(f"Dropping duplicate terminal event {event_type} for {req_id}")
        return False
    _event(req_id, event_type, data)
    return True


# ---------------------------------------------------------------------------
# Bridge state
# ---------------------------------------------------------------------------

class BridgeState:
    """Holds cached config, active agent, abort state, and shared sandbox manager."""

    def __init__(self) -> None:
        self.config = None  # lazy-loaded
        self._lock = threading.Lock()
        self._active_agent: Any = None
        self._active_req_id: str | None = None
        self._terminated: set[str] = set()
        self._pending_approvals: dict[str, threading.Event] = {}
        self._approval_decisions: dict[str, str] = {}
        self._approval_meta: dict[str, dict] = {}
        self._sandbox_manager: Any = None  # shared SandboxManager across agents
        self._event_emitter: Any = None  # Phase 1 shared EventEmitter
        self._agent_control: Any = None  # Phase 2 shared AgentControl
        self._orchestrator: Any = None  # Phase 3 shared ToolOrchestrator

    def load_config(self):
        from miqi.config.loader import load_config

        self.config = load_config()
        return self.config

    def _ensure_sandbox_manager(self):
        """Lazy-init the shared SandboxManager from config."""
        if self._sandbox_manager is not None:
            return
        config = self.load_config()
        sb_cfg = getattr(config.tools, "sandbox", None)
        if sb_cfg is None or not getattr(sb_cfg, "enabled", True):
            self._sandbox_manager = "disabled"
            return
        from miqi.sandbox.manager import SandboxManager
        self._sandbox_manager = SandboxManager(
            workspace=config.workspace_path,
            share_net=getattr(sb_cfg, "share_net", False),
            enabled=getattr(sb_cfg, "enabled", True),
            max_sandboxes=getattr(sb_cfg, "max_sandboxes", 10),
            auto_cleanup=getattr(sb_cfg, "auto_cleanup", True),
            wsl_distro=getattr(sb_cfg, "wsl_distro", ""),
            wsl_base_dir=getattr(sb_cfg, "wsl_base_dir", "/tmp/miqi-sandboxes"),
        )

    def build_agent(self, session_key: str, approval_callback=None):
        """Create an AgentLoop for the given session."""
        from miqi.agent.loop import AgentLoop
        from miqi.bus.queue import MessageBus

        config = self.load_config()
        provider = config.build_provider(config.agents.defaults.model)
        if provider is None:
            raise RuntimeError(
                f"No provider configured for model '{config.agents.defaults.model}'. "
                "Run setup first."
            )

        defaults = config.agents.defaults
        bus = MessageBus()

        self._ensure_sandbox_manager()
        # Pass the shared manager so all agents reuse the same sandbox pool
        sandbox_mgr = None if self._sandbox_manager == "disabled" else self._sandbox_manager

        agent = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=config.workspace_path,
            agent_name=defaults.name,
            model=defaults.model,
            max_iterations=defaults.max_tool_iterations,
            temperature=defaults.temperature,
            max_tokens=defaults.max_tokens,
            memory_window=defaults.memory_window,
            reflect_after_tool_calls=defaults.reflect_after_tool_calls,
            max_tool_result_chars=defaults.max_tool_result_chars,
            context_limit_chars=defaults.context_limit_chars,
            memory_config=config.agents.memory,
            self_improvement_config=config.agents.self_improvement,
            session_config=config.agents.sessions,
            exec_config=config.tools.exec,
            web_config=config.tools.web,
            paper_config=config.tools.papers,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            mcp_servers={},
            channels_config=config.channels,
            smart_routing_config=config.agents.smart_routing,
            approval_callback=approval_callback,
            session_key=session_key,
            sandbox_manager=sandbox_mgr,
        )
        return agent

    def set_active(self, agent: Any, req_id: str) -> None:
        with self._lock:
            self._active_agent = agent
            self._active_req_id = req_id

    def destroy_sandbox(self, session_key: str) -> bool:
        """Destroy the sandbox for a session (called on delete/archive)."""
        if self._sandbox_manager is None or self._sandbox_manager == "disabled":
            return False
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self._sandbox_manager.destroy(session_key))
            finally:
                loop.close()
            return result
        except Exception as exc:
            _log(f"destroy_sandbox error: {exc}")
            return False

    def abort_active(self) -> dict:
        with self._lock:
            agent = self._active_agent
            req_id = self._active_req_id
            self._active_agent = None
            self._active_req_id = None
        # Wake all pending approvals so the blocked chat daemon thread can exit.
        # Without this, a thread waiting on evt.wait() in _desktop_approval_callback
        # would remain stuck until the approval timeout expires.
        pending_ids = self.list_pending_approval_ids()
        for aid in pending_ids:
            self.resolve_approval(aid, "deny")
        if agent is not None:
            agent._abort_event.set()
            agent.stop()
            return {"aborted": True, "req_id": req_id}
        return {"aborted": False}

    def mark_terminated(self, req_id: str) -> bool:
        """Atomically check-and-mark a request as terminated.

        Returns True if this call is the first to mark the request,
        False if it was already terminated by a concurrent path (e.g. abort
        raced natural completion).
        """
        with self._lock:
            if req_id in self._terminated:
                return False
            self._terminated.add(req_id)
            return True

    def register_approval(self, approval_id: str, meta: dict | None = None) -> threading.Event:
        """Create and store an event for a pending approval. Returns the event."""
        evt = threading.Event()
        with self._lock:
            self._pending_approvals[approval_id] = evt
            if meta:
                meta["created_at"] = time.time()
                self._approval_meta[approval_id] = meta
        return evt

    def resolve_approval(self, approval_id: str, decision: str) -> bool:
        """Set the decision and unblock the waiting callback. Returns True if found."""
        with self._lock:
            evt = self._pending_approvals.pop(approval_id, None)
            self._approval_meta.pop(approval_id, None)
            if evt is None:
                return False
            self._approval_decisions[approval_id] = decision
        evt.set()
        return True

    def get_approval_decision(self, approval_id: str) -> str:
        """Retrieve and remove the stored decision. Returns 'deny' if not found."""
        with self._lock:
            return self._approval_decisions.pop(approval_id, "deny")

    def list_pending_approval_ids(self) -> list[str]:
        with self._lock:
            return list(self._pending_approvals.keys())

    def list_pending_approvals(self) -> list[dict]:
        """Return pending approvals with metadata for display."""
        import time as _time
        now = _time.time()
        result: list[dict] = []
        with self._lock:
            for aid in list(self._pending_approvals.keys()):
                meta = self._approval_meta.get(aid, {})
                result.append({
                    "approval_id": aid,
                    "command": meta.get("command", ""),
                    "description": meta.get("description", ""),
                    "allow_permanent": meta.get("allow_permanent", True),
                    "created_at": meta.get("created_at", now),
                    "age_seconds": now - meta.get("created_at", now),
                })
        return result


_state = BridgeState()

from miqi.agent.tools.filesystem import (
    _delete_snapshot,
    _snapshots_lock,
    _maybe_snapshot,
    _restore_snapshot,
    _read_snapshot,
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_status(req_id: str, params: dict) -> None:
    config_exists = Path.home() / ".miqi" / "config.json"
    _result(req_id, {
        "status": "ok",
        "configured": config_exists.exists(),
        "python_version": sys.version,
    })


def handle_chat_send(req_id: str, params: dict) -> None:
    content = params["content"]
    session_key = params.get("session_key", "desktop:default")

    def _run_in_thread() -> None:
        async def _run() -> None:
            # Build desktop approval callback (blocks thread, sends event to renderer)
            config = _state.load_config()
            approval_timeout = config.agents.command_approval.timeout
            approval_enabled = config.agents.command_approval.enabled

            def _desktop_approval_callback(command: str, description: str, *, allow_permanent: bool = True) -> str:
                if not approval_enabled:
                    return "once"
                approval_id = str(uuid.uuid4())
                evt = _state.register_approval(approval_id, {
                    "command": command,
                    "description": description,
                    "allow_permanent": allow_permanent,
                })
                _event(req_id, "approval_request", {
                    "approval_id": approval_id,
                    "command": command,
                    "description": description,
                    "allow_permanent": allow_permanent,
                })
                if not evt.wait(timeout=approval_timeout):
                    _state.resolve_approval(approval_id, "deny")
                    return "deny"
                return _state.get_approval_decision(approval_id)

            agent = _state.build_agent(session_key, approval_callback=_desktop_approval_callback)

            # Phase 1: wire EventEmitter for typed events (dual-emit)
            if _state._event_emitter is None:
                from miqi.bridge.event_emitter import EventEmitter

                def _bridge_send_event(channel: str, data: dict) -> None:
                    _send({
                        "type": channel,
                        "data": data,
                    })

                _state._event_emitter = EventEmitter(_bridge_send_event)
                _log("Typed event protocol enabled (Phase 1 dual-emit)")
            agent.enable_typed_events(_state._event_emitter)

            # Phase 2: initialize shared AgentControl
            if _state._agent_control is None:
                from miqi.runtime.agent_registry import AgentRegistry
                from miqi.runtime.agent_control import AgentControl
                registry = AgentRegistry()
                _state._agent_control = AgentControl(
                    session_id=session_key,
                    registry=registry,
                    event_emitter=_state._event_emitter,
                    workspace=config.workspace_path,
                )
                _log("Multi-agent runtime enabled (Phase 2)")

            # Phase 3: initialize shared ToolOrchestrator
            if _state._orchestrator is None:
                from miqi.execution.orchestrator import ToolOrchestrator
                from miqi.execution.permission_engine import PermissionEngine
                from miqi.execution.sandbox_policy import SandboxPolicyEngine
                from miqi.execution.hook_runtime import HookRuntime

                bwrap_ok = (
                    _state._sandbox_manager is not None
                    and _state._sandbox_manager != "disabled"
                )

                _state._orchestrator = ToolOrchestrator(
                    permission_engine=PermissionEngine(
                        permanent_allowlist=set(_state._approval_meta.keys()),
                    ),
                    sandbox_engine=SandboxPolicyEngine(
                        bwrap_available=bwrap_ok,
                    ),
                    hook_runtime=HookRuntime(),
                    tool_registry=None,
                    event_emitter=_state._event_emitter,
                )
                _log("Tool orchestration engine enabled (Phase 3)")

            # Wire orchestrator into agent
            agent._orchestrator = _state._orchestrator
            if _state._orchestrator.tool_registry is None:
                _state._orchestrator.tool_registry = agent.tools

            _state.set_active(agent, req_id)

            async def on_progress(text: str, tool_hint: bool = False) -> None:
                _event(req_id, "progress", {"text": text, "tool_hint": tool_hint})

            try:
                result = await agent.process_direct(
                    content=content,
                    session_key=session_key,
                    channel="desktop",
                    chat_id=session_key,
                    on_progress=on_progress,
                )
                aborted = agent._abort_event.is_set()
                _terminal_event(req_id, "final", {"content": result, "aborted": aborted})
            except Exception as exc:
                _log(f"chat.send error: {exc}")
                _terminal_event(req_id, "error", {"message": str(exc)})
            finally:
                _state.set_active(None, "")
                # Stop the agent to clean up sandbox resources
                try:
                    agent.stop()
                except Exception as exc:
                    _log(f"agent.stop error: {exc}")

        asyncio.run(_run())

    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()
    _result(req_id, {"accepted": True})


def handle_chat_abort(req_id: str, params: dict) -> None:
    result = _state.abort_active()
    aborted = result["aborted"]
    active_req_id = result.get("req_id")
    if aborted and active_req_id:
        # Notify frontend to dismiss any orphan approval modal immediately
        _event(active_req_id, "approval_cleared", {"reason": "abort"})
        _terminal_event(active_req_id, "aborted", {"message": "Chat aborted by user"})
    _result(req_id, {"aborted": aborted})


def handle_sessions_list(req_id: str, params: dict) -> None:
    config = _state.load_config()
    from miqi.session.manager import SessionManager

    sm = SessionManager(config.workspace_path)
    sessions = sm.list_sessions()
    _result(req_id, {"sessions": sessions})


def handle_sessions_get(req_id: str, params: dict) -> None:
    session_key = params["session_key"]
    config = _state.load_config()
    from miqi.session.manager import SessionManager

    sm = SessionManager(config.workspace_path)
    session = sm.get_or_create(session_key)
    _result(req_id, {
        "key": session.key,
        "messages": session.messages,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "metadata": session.metadata,
    })


def handle_sessions_delete(req_id: str, params: dict) -> None:
    session_key = params["session_key"]
    config = _state.load_config()
    from miqi.session.manager import SessionManager

    sm = SessionManager(config.workspace_path)
    deleted = sm.delete(session_key)
    # Also destroy the sandbox for this session
    _state.destroy_sandbox(session_key)
    _result(req_id, {"deleted": deleted})


def handle_sessions_archive(req_id: str, params: dict) -> None:
    """Archive a session — hide it from the default session list."""
    session_key = params.get("session_key", "")
    if not session_key:
        _error(req_id, "session_key is required")
        return
    try:
        sm = _get_session_manager()
        sm.archive(session_key)
        # Destroy sandbox when archiving (auto_cleanup logic)
        _state.destroy_sandbox(session_key)
        _result(req_id, {"archived": True})
    except Exception as exc:
        _error(req_id, str(exc))


def handle_sessions_unarchive(req_id: str, params: dict) -> None:
    """Unarchive a session — restore it to the default session list."""
    session_key = params.get("session_key", "")
    if not session_key:
        _error(req_id, "session_key is required")
        return
    try:
        sm = _get_session_manager()
        sm.unarchive(session_key)
        _result(req_id, {"unarchived": True})
    except Exception as exc:
        _error(req_id, str(exc))


def handle_sessions_list_archived(req_id: str, params: dict) -> None:
    """List only archived sessions."""
    try:
        sm = _get_session_manager()
        sessions = sm.list_sessions(include_archived=True)
        # Filter to only archived ones (non-archived won't have .archived marker)
        archived = []
        for s in sessions:
            from miqi.session.manager import safe_filename
            safe_key = safe_filename(s["key"].replace(":", "_"))
            marker = sm.sessions_dir / safe_key / ".archived"
            if marker.exists():
                archived.append(s)
        _result(req_id, {"sessions": archived})
    except Exception as exc:
        _error(req_id, str(exc))


def handle_sessions_get_tracked_files(req_id: str, params: dict) -> None:
    """Return tracked files for a session from tracked_files.json."""
    session_key = params.get("session_key", "")
    if not session_key:
        _error(req_id, "session_key is required")
        return
    try:
        sm = _get_session_manager()
        files = sm.load_tracked_files(session_key)
        # Convert to array for frontend
        result = [
            {"path": path, **info}
            for path, info in files.items()
        ]
        _result(req_id, {"tracked_files": result})
    except Exception as exc:
        _error(req_id, str(exc))


def handle_sessions_clear_tracked_files(req_id: str, params: dict) -> None:
    """Remove all tracked file entries for a session."""
    session_key = params.get("session_key", "")
    if not session_key:
        _error(req_id, "session_key is required")
        return
    try:
        sm = _get_session_manager()
        sm.clear_tracked_files(session_key)
        _result(req_id, {"cleared": True})
    except Exception as exc:
        _error(req_id, str(exc))


def handle_config_get(req_id: str, params: dict) -> None:
    config = _state.load_config()
    data = config.model_dump(by_alias=True)
    _redact_secrets(data)
    _result(req_id, data)


def handle_config_update(req_id: str, params: dict) -> None:
    from miqi.config.loader import save_config
    from miqi.config.schema import Config

    updates = params.get("config", {})
    current = _state.load_config()
    merged = _deep_merge(current.model_dump(by_alias=True), updates)
    new_config = Config.model_validate(merged)
    save_config(new_config)
    _state.config = new_config
    _result(req_id, {"saved": True})


def handle_providers_list(req_id: str, params: dict) -> None:
    from miqi.providers.registry import PROVIDERS

    config = _state.load_config()
    _model = config.agents.defaults.model
    _model_provider = config.get_provider_name(_model)
    providers_out = []
    for spec in PROVIDERS:
        pc = getattr(config.providers, spec.name, None)
        _api_key = pc.api_key if pc else None
        _hint = None
        if _api_key and len(_api_key) >= 8:
            _hint = _api_key[:4] + "…" + _api_key[-4:]
        elif _api_key:
            _hint = "***"
        providers_out.append({
            "name": spec.name,
            "display_name": spec.display_name or spec.name.title(),
            "env_key": spec.env_key,
            "provider_type": spec.provider_type,
            "is_gateway": spec.is_gateway,
            "is_local": spec.is_local,
            "default_api_base": spec.default_api_base,
            "configured": bool(pc and (pc.api_key or pc.api_base)),
            "api_key_hint": _hint,
            "api_base": pc.api_base if pc else None,
            "configured_model": _model if _model_provider == spec.name else None,
        })
    _result(req_id, {"providers": providers_out})


def handle_providers_test(req_id: str, params: dict) -> None:
    provider_name = params.get("provider_name", "")
    api_key = params.get("api_key") or ""
    api_base = params.get("api_base") or None

    # If no API key provided, read from current saved config
    if not api_key:
        config = _state.load_config()
        pc = getattr(config.providers, provider_name, None)
        if pc is not None:
            api_key = pc.api_key or ""
            if not api_base:
                api_base = pc.api_base

    if not api_key:
        _error(req_id, "No API key configured — enter one in Edit or save a provider first")
        return

    async def _test() -> None:
        from miqi.providers.registry import find_by_name

        spec = find_by_name(provider_name)
        if spec is None:
            _error(req_id, f"Unknown provider: {provider_name}")
            return

        if spec.provider_type == "anthropic":
            from miqi.providers.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider(api_key=api_key, api_base=api_base, provider_name=provider_name)
        elif spec.provider_type == "gemini":
            from miqi.providers.gemini_provider import GeminiProvider
            provider = GeminiProvider(api_key=api_key, api_base=api_base, provider_name=provider_name)
        else:
            from miqi.providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key=api_key, api_base=api_base, provider_name=provider_name)

        try:
            response = await provider.chat(
                messages=[{"role": "user", "content": "Hello, respond with just 'ok'."}],
                model=provider.get_default_model(),
                max_tokens=16,
                temperature=0.0,
            )
            ok = response.content is not None and len(response.content) > 0
            _result(req_id, {"ok": ok, "model": provider.get_default_model()})
        except Exception as exc:
            _error(req_id, str(exc))

    asyncio.run(_test())


def handle_providers_update(req_id: str, params: dict) -> None:
    """Update a single provider's api_key / api_base / extra_headers in config."""
    from miqi.config.loader import save_config

    provider_name = params.get("provider_name", "").strip()
    if not provider_name:
        _error(req_id, "provider_name is required")
        return

    from miqi.config.schema import ProvidersConfig
    valid_names = set(ProvidersConfig.model_fields.keys())
    if provider_name not in valid_names:
        _error(req_id, f"Unknown provider: {provider_name}")
        return

    config = _state.load_config()
    pc = getattr(config.providers, provider_name, None)
    if pc is None:
        _error(req_id, f"Provider config not found: {provider_name}")
        return

    update: dict = {}
    if "api_key" in params:
        update["api_key"] = str(params["api_key"])
    if "api_base" in params:
        v = params["api_base"]
        update["api_base"] = str(v) if v else None
    if "extra_headers" in params:
        v = params["extra_headers"]
        update["extra_headers"] = dict(v) if v else None

    model_override: str | None = None
    if "model" in params and params["model"]:
        model_override = str(params["model"]).strip()

    if not update and not model_override:
        _error(req_id, "No fields to update")
        return

    if update:
        current_dict = pc.model_dump(by_alias=False)
        current_dict.update(update)

        from miqi.config.schema import ProviderConfig
        new_pc = ProviderConfig.model_validate(current_dict)
        setattr(config.providers, provider_name, new_pc)

    if model_override:
        config.agents.defaults.model = model_override

    save_config(config)
    _state.config = config
    _result(req_id, {"saved": True, "provider_name": provider_name})


def handle_channels_list(req_id: str, params: dict) -> None:
    """Return current channels config as a serializable dict, with secrets redacted."""
    config = _state.load_config()
    data = config.channels.model_dump(by_alias=False)
    _redact_secrets(data)
    _result(req_id, {"channels": data})


def handle_channels_update(req_id: str, params: dict) -> None:
    """Merge partial update into channels config and save."""
    from miqi.config.loader import save_config

    updates = params.get("channels", {})
    if not isinstance(updates, dict):
        _error(req_id, "channels must be a dict")
        return

    config = _state.load_config()
    from miqi.config.schema import ChannelsConfig

    current = config.channels.model_dump(by_alias=False)
    merged = _deep_merge(current, updates)
    config.channels = ChannelsConfig.model_validate(merged)
    save_config(config)
    _state.config = config
    _result(req_id, {"saved": True})


def handle_approvals_list(req_id: str, params: dict) -> None:
    from miqi.agent.command_approval import (
        get_permanent_allowlist, get_permanent_allowlist_meta,
    )
    config = _state.load_config()
    pending = _state.list_pending_approvals()
    permanent_patterns = sorted(get_permanent_allowlist())
    permanent_meta = get_permanent_allowlist_meta()
    permanent_entries = [
        {
            "pattern": p,
            "added_at": permanent_meta.get(p, 0),
        }
        for p in permanent_patterns
    ]
    _result(req_id, {
        "pending": pending,
        "pending_ids": [p["approval_id"] for p in pending],
        "permanent_allowlist": permanent_patterns,
        "permanent_entries": permanent_entries,
        "enabled": config.agents.command_approval.enabled,
        "timeout": config.agents.command_approval.timeout,
    })


def handle_approvals_resolve(req_id: str, params: dict) -> None:
    approval_id = params.get("approval_id", "")
    decision = params.get("decision", "deny")
    if decision not in ("once", "session", "always", "deny"):
        _error(req_id, f"Invalid decision: {decision}")
        return
    found = _state.resolve_approval(approval_id, decision)
    _result(req_id, {"resolved": found, "approval_id": approval_id})


def handle_approvals_clear_permanent(req_id: str, params: dict) -> None:
    from miqi.agent.command_approval import (
        _lock, _permanent_approved, _permanent_added_at,
    )
    pattern = params.get("pattern")
    with _lock:
        if pattern:
            _permanent_approved.discard(pattern)
            _permanent_added_at.pop(pattern, None)
        else:
            _permanent_approved.clear()
            _permanent_added_at.clear()
    _result(req_id, {"cleared": True})


def handle_approvals_add_permanent(req_id: str, params: dict) -> None:
    from miqi.agent.command_approval import (
        approve_permanent, _save_permanent_allowlist,
    )
    pattern = params.get("pattern", "").strip()
    if not pattern:
        _error(req_id, "pattern is required")
        return
    approve_permanent(pattern)
    _save_permanent_allowlist()
    _result(req_id, {"added": True, "pattern": pattern})


def handle_approvals_history(req_id: str, params: dict) -> None:
    from miqi.agent.command_approval import get_approval_history
    limit = params.get("limit", 200)
    history = get_approval_history(limit)
    _result(req_id, {"history": history})


# ---------------------------------------------------------------------------
# Cron handlers
# ---------------------------------------------------------------------------

def _get_cron_service():
    """Create a CronService pointed at the standard data dir."""
    from miqi.config.loader import get_data_dir
    from miqi.cron.service import CronService

    config = _state.load_config()
    store_path = get_data_dir() / "cron" / "jobs.json"
    return CronService(store_path, job_timeout=config.cron.job_timeout_seconds)


def _job_to_dict(job) -> dict:
    """Serialize a CronJob to a dict with camelCase keys for the frontend."""
    return {
        "id": job.id,
        "name": job.name,
        "enabled": job.enabled,
        "schedule": {
            "kind": job.schedule.kind,
            "atMs": job.schedule.at_ms,
            "everyMs": job.schedule.every_ms,
            "expr": job.schedule.expr,
            "tz": job.schedule.tz,
        },
        "payload": {
            "kind": job.payload.kind,
            "message": job.payload.message,
            "deliver": job.payload.deliver,
            "channel": job.payload.channel,
            "to": job.payload.to,
        },
        "state": {
            "nextRunAtMs": job.state.next_run_at_ms,
            "lastRunAtMs": job.state.last_run_at_ms,
            "lastStatus": job.state.last_status,
            "lastError": job.state.last_error,
        },
        "createdAtMs": job.created_at_ms,
        "updatedAtMs": job.updated_at_ms,
        "deleteAfterRun": job.delete_after_run,
    }


def handle_cron_list(req_id: str, params: dict) -> None:
    service = _get_cron_service()
    jobs = service.list_jobs(include_disabled=True)
    _result(req_id, {"jobs": [_job_to_dict(j) for j in jobs]})


def handle_cron_create(req_id: str, params: dict) -> None:
    from miqi.cron.types import CronSchedule

    name = params.get("name", "").strip()
    if not name:
        _error(req_id, "name is required")
        return

    schedule_kind = params.get("scheduleKind", "every")
    if schedule_kind not in ("at", "every", "cron"):
        _error(req_id, f"Invalid schedule kind: {schedule_kind}")
        return

    try:
        schedule = CronSchedule(kind=schedule_kind)
        if schedule_kind == "at":
            at_ms = params.get("atMs")
            if not at_ms:
                _error(req_id, "atMs is required for at schedules")
                return
            schedule.at_ms = int(at_ms)
        elif schedule_kind == "every":
            every_ms = params.get("everyMs")
            if not every_ms:
                _error(req_id, "everyMs is required for every schedules")
                return
            schedule.every_ms = int(every_ms)
        elif schedule_kind == "cron":
            expr = params.get("expr", "").strip()
            if not expr:
                _error(req_id, "expr is required for cron schedules")
                return
            schedule.expr = expr
            schedule.tz = params.get("tz") or None

        service = _get_cron_service()
        job = service.add_job(
            name=name,
            schedule=schedule,
            message=params.get("message", ""),
            deliver=bool(params.get("deliver", False)),
            channel=params.get("channel") or None,
            to=params.get("to") or None,
        )
        _result(req_id, {"job": _job_to_dict(job)})
    except ValueError as exc:
        _error(req_id, str(exc))


def handle_cron_update(req_id: str, params: dict) -> None:
    job_id = params.get("jobId", "").strip()
    if not job_id:
        _error(req_id, "jobId is required")
        return

    service = _get_cron_service()
    jobs = service.list_jobs(include_disabled=True)
    target = None
    for j in jobs:
        if j.id == job_id:
            target = j
            break

    if target is None:
        _error(req_id, f"Job not found: {job_id}")
        return

    if "name" in params:
        target.name = params["name"].strip()
    if "message" in params:
        target.payload.message = params.get("message", "")
    if "deliver" in params:
        target.payload.deliver = bool(params.get("deliver"))
    if "channel" in params:
        target.payload.channel = params.get("channel") or None
    if "to" in params:
        target.payload.to = params.get("to") or None

    # Schedule updates
    if "scheduleKind" in params:
        kind = params["scheduleKind"]
        if kind not in ("at", "every", "cron"):
            _error(req_id, f"Invalid schedule kind: {kind}")
            return
        from miqi.cron.types import _validate_schedule_for_add

        target.schedule.kind = kind
        if kind == "at" and "atMs" in params:
            target.schedule.at_ms = int(params["atMs"])
            target.schedule.every_ms = None
            target.schedule.expr = None
            target.schedule.tz = None
        elif kind == "every" and "everyMs" in params:
            target.schedule.every_ms = int(params["everyMs"])
            target.schedule.at_ms = None
            target.schedule.expr = None
            target.schedule.tz = None
        elif kind == "cron":
            if "expr" in params:
                target.schedule.expr = params["expr"].strip()
            target.schedule.at_ms = None
            target.schedule.every_ms = None
            target.schedule.tz = params.get("tz") or None

        try:
            _validate_schedule_for_add(target.schedule)
        except ValueError as exc:
            _error(req_id, str(exc))
            return

        # Recompute next run
        from miqi.cron.service import _compute_next_run, _now_ms
        target.state.next_run_at_ms = _compute_next_run(target.schedule, _now_ms())

    target.updated_at_ms = int(time.time() * 1000)
    service._save_store()
    _result(req_id, {"job": _job_to_dict(target)})


def handle_cron_delete(req_id: str, params: dict) -> None:
    job_id = params.get("jobId", "").strip()
    if not job_id:
        _error(req_id, "jobId is required")
        return

    service = _get_cron_service()
    removed = service.remove_job(job_id)
    _result(req_id, {"deleted": removed})


def handle_cron_toggle(req_id: str, params: dict) -> None:
    job_id = params.get("jobId", "").strip()
    if not job_id:
        _error(req_id, "jobId is required")
        return

    enabled = bool(params.get("enabled", True))
    service = _get_cron_service()
    job = service.enable_job(job_id, enabled=enabled)
    if job is None:
        _error(req_id, f"Job not found: {job_id}")
        return
    _result(req_id, {"job": _job_to_dict(job)})


def handle_cron_run(req_id: str, params: dict) -> None:
    job_id = params.get("jobId", "").strip()
    if not job_id:
        _error(req_id, "jobId is required")
        return

    async def _run():
        service = _get_cron_service()
        ok = await service.run_job(job_id, force=True)
        if not ok:
            _error(req_id, f"Job not found: {job_id}")
            return
        # Re-fetch to return updated state
        jobs = service.list_jobs(include_disabled=True)
        for j in jobs:
            if j.id == job_id:
                _result(req_id, {"job": _job_to_dict(j)})
                return
        _error(req_id, f"Job disappeared: {job_id}")

    asyncio.run(_run())


def handle_cron_runs(req_id: str, params: dict) -> None:
    job_id = params.get("jobId", "").strip()
    service = _get_cron_service()
    jobs = service.list_jobs(include_disabled=True)

    if job_id:
        jobs = [j for j in jobs if j.id == job_id]

    runs = []
    for j in jobs:
        if j.state.last_run_at_ms:
            runs.append({
                "jobId": j.id,
                "jobName": j.name,
                "startedAtMs": j.state.last_run_at_ms,
                "status": j.state.last_status,
                "error": j.state.last_error,
            })

    runs.sort(key=lambda r: r["startedAtMs"], reverse=True)
    _result(req_id, {"runs": runs})


# ---------------------------------------------------------------------------
# Memory handlers
# ---------------------------------------------------------------------------

def _get_memory_dir() -> Path:
    """Return the workspace memory directory."""
    config = _state.load_config()
    return config.workspace_path / "memory"


def _validate_memory_path(file_path: str) -> Path:
    """Validate and resolve a memory file path, preventing directory traversal."""
    memory_dir = _get_memory_dir()
    # Resolve the requested path relative to memory dir
    resolved = (memory_dir / file_path).resolve()
    # Must be within the memory directory
    if not str(resolved).startswith(str(memory_dir.resolve())):
        raise ValueError(f"Path escapes memory directory: {file_path}")
    return resolved


def handle_memory_list(req_id: str, params: dict) -> None:
    memory_dir = _get_memory_dir()
    files: list[dict] = []

    # Editable markdown files
    if memory_dir.exists():
        for f in sorted(memory_dir.glob("*.md")):
            files.append({
                "path": f.name,
                "scope": "workspace" if f.name != "MEMORY.md" else "agent",
                "size": f.stat().st_size,
                "updatedAtMs": int(f.stat().st_mtime * 1000),
            })
        # Also list MEMORY.md if it exists (it's the legacy long-term file)
        mem_file = memory_dir / "MEMORY.md"
        if mem_file.exists() and "MEMORY.md" not in {f["path"] for f in files}:
            files.insert(0, {
                "path": "MEMORY.md",
                "scope": "agent",
                "size": mem_file.stat().st_size,
                "updatedAtMs": int(mem_file.stat().st_mtime * 1000),
            })

    _result(req_id, {"files": files})


def handle_memory_get(req_id: str, params: dict) -> None:
    file_path = params.get("path", "").strip()
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_memory_path(file_path)
    except ValueError as exc:
        _error(req_id, str(exc))
        return

    if not resolved.exists():
        _error(req_id, f"File not found: {file_path}")
        return

    content = resolved.read_text(encoding="utf-8")
    _result(req_id, {
        "path": file_path,
        "content": content,
        "size": len(content),
    })


def handle_memory_update(req_id: str, params: dict) -> None:
    file_path = params.get("path", "").strip()
    content = params.get("content", "")
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_memory_path(file_path)
    except ValueError as exc:
        _error(req_id, str(exc))
        return

    # Only allow .md files for safety
    if resolved.suffix not in (".md",):
        _error(req_id, "Only .md files can be edited")
        return

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    _result(req_id, {"saved": True, "path": file_path})


def handle_memory_delete(req_id: str, params: dict) -> None:
    """Delete a memory file."""
    file_path = params.get("path", "").strip()
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_memory_path(file_path)
    except ValueError as exc:
        _error(req_id, str(exc))
        return

    if not resolved.exists():
        _error(req_id, f"File not found: {file_path}")
        return

    if resolved.suffix not in (".md",):
        _error(req_id, "Only .md files can be deleted")
        return

    resolved.unlink()
    _result(req_id, {"deleted": True, "path": file_path})


def handle_memory_lessons(req_id: str, params: dict) -> None:
    from miqi.agent.memory import MemoryStore

    config = _state.load_config()
    memory = MemoryStore(
        workspace=config.workspace_path,
        self_improvement_enabled=config.agents.self_improvement.enabled,
        max_lessons=config.agents.self_improvement.max_lessons,
        min_lesson_confidence=config.agents.self_improvement.min_lesson_confidence,
        max_lessons_in_prompt=config.agents.self_improvement.max_lessons_in_prompt,
        lesson_stale_days=config.agents.self_improvement.lesson_stale_days,
        lesson_archive_days=config.agents.self_improvement.lesson_archive_days,
        feedback_max_message_chars=config.agents.self_improvement.feedback_max_message_chars,
        feedback_require_prefix=config.agents.self_improvement.feedback_require_prefix,
        promotion_enabled=config.agents.self_improvement.promotion_enabled,
        promotion_min_users=config.agents.self_improvement.promotion_min_users,
        promotion_triggers=config.agents.self_improvement.promotion_triggers,
    )
    lessons = memory.list_lessons(scope="all", limit=100, include_disabled=True)
    result = []
    for lesson in lessons:
        result.append({
            "id": str(lesson.get("id", "")),
            "trigger": str(lesson.get("trigger", "")),
            "badAction": str(lesson.get("bad_action", "")),
            "betterAction": str(lesson.get("better_action", "")),
            "scope": str(lesson.get("scope", "session")),
            "sessionKey": lesson.get("session_key"),
            "confidence": lesson.get("confidence", 0),
            "effectiveConfidence": lesson.get("effective_confidence", 0),
            "hits": lesson.get("hits", 0),
            "state": str(lesson.get("state", "active")),
            "enabled": lesson.get("enabled", True),
            "source": str(lesson.get("source", "")),
            "createdAt": str(lesson.get("created_at", "")),
            "updatedAt": str(lesson.get("updated_at", "")),
        })
    _result(req_id, {"lessons": result})


def handle_memory_lesson_unlearn(req_id: str, params: dict) -> None:
    from miqi.agent.memory import MemoryStore

    lesson_id = str(params.get("lesson_id", ""))
    if not lesson_id:
        _error(req_id, "lesson_id is required")
        return

    config = _state.load_config()
    memory = MemoryStore(
        workspace=config.workspace_path,
        self_improvement_enabled=config.agents.self_improvement.enabled,
        max_lessons=config.agents.self_improvement.max_lessons,
        min_lesson_confidence=config.agents.self_improvement.min_lesson_confidence,
        max_lessons_in_prompt=config.agents.self_improvement.max_lessons_in_prompt,
        lesson_stale_days=config.agents.self_improvement.lesson_stale_days,
        lesson_archive_days=config.agents.self_improvement.lesson_archive_days,
        feedback_max_message_chars=config.agents.self_improvement.feedback_max_message_chars,
        feedback_require_prefix=config.agents.self_improvement.feedback_require_prefix,
        promotion_enabled=config.agents.self_improvement.promotion_enabled,
        promotion_min_users=config.agents.self_improvement.promotion_min_users,
        promotion_triggers=config.agents.self_improvement.promotion_triggers,
    )
    success = memory._lesson_store.unlearn_by_id(lesson_id)
    if success:
        memory.flush()
    _result(req_id, {"unlearned": [lesson_id] if success else []})


# ---------------------------------------------------------------------------
# Experience handlers
# ---------------------------------------------------------------------------

_experience_store = None

def _get_experience_store():
    """Lazy-init ExperienceStore singleton from current config."""
    global _experience_store
    if _experience_store is not None:
        return _experience_store

    from miqi.agent.memory.experience_store import ExperienceStore
    from miqi.agent.memory import MemoryStore
    from miqi.agent.trace.store import TraceStore

    config = _state.load_config()
    memory = MemoryStore(
        workspace=config.workspace_path,
        self_improvement_enabled=config.agents.self_improvement.enabled,
        max_lessons=config.agents.self_improvement.max_lessons,
        min_lesson_confidence=config.agents.self_improvement.min_lesson_confidence,
        max_lessons_in_prompt=config.agents.self_improvement.max_lessons_in_prompt,
        lesson_stale_days=config.agents.self_improvement.lesson_stale_days,
        lesson_archive_days=config.agents.self_improvement.lesson_archive_days,
        feedback_max_message_chars=config.agents.self_improvement.feedback_max_message_chars,
        feedback_require_prefix=config.agents.self_improvement.feedback_require_prefix,
        promotion_enabled=config.agents.self_improvement.promotion_enabled,
        promotion_min_users=config.agents.self_improvement.promotion_min_users,
        promotion_triggers=config.agents.self_improvement.promotion_triggers,
        lessons_legacy_inject_enabled=config.agents.self_improvement.lessons_legacy_inject_enabled,
    )
    trace = TraceStore(
        workspace=config.workspace_path,
        enabled=config.agents.self_improvement.trace_enabled,
        embedding_model=config.agents.self_improvement.embedding_model,
        recover=False,
    )
    _experience_store = ExperienceStore(memory_store=memory, trace_store=trace)
    return _experience_store


def handle_experience_list(req_id: str, params: dict) -> None:
    entry_type = params.get("type")       # "fact" | "rule" | "trace" | None
    scope = params.get("scope")           # "session" | "global" | None
    session_key = params.get("session_key")  # str | None
    limit = int(params.get("limit", 100))

    store = _get_experience_store()
    entries = store.list_entries(type=entry_type, scope=scope,
                                  session_key=session_key, limit=limit)
    _result(req_id, {"entries": entries})


def handle_experience_delete(req_id: str, params: dict) -> None:
    entry_type = params["type"]
    entry_id = params["id"]
    store = _get_experience_store()
    ok = store.delete_entry(entry_type, entry_id)
    _result(req_id, {"ok": ok})


def handle_experience_toggle(req_id: str, params: dict) -> None:
    entry_type = params["type"]
    entry_id = params["id"]
    enabled = bool(params["enabled"])
    store = _get_experience_store()
    ok = store.toggle_entry(entry_type, entry_id, enabled)
    _result(req_id, {"ok": ok})


def handle_experience_search(req_id: str, params: dict) -> None:
    query = str(params.get("query", ""))
    entry_type = params.get("type")
    limit = int(params.get("limit", 10))
    store = _get_experience_store()
    entries = store.search_entries(query, type=entry_type, limit=limit)
    _result(req_id, {"entries": entries})


# ---------------------------------------------------------------------------
# Skills handlers
# ---------------------------------------------------------------------------

def _get_skills_loader():
    from miqi.agent.skills import SkillsLoader

    config = _state.load_config()
    return SkillsLoader(workspace=config.workspace_path)


def handle_skills_list(req_id: str, params: dict) -> None:
    loader = _get_skills_loader()
    all_skills = loader.list_skills(filter_unavailable=False)
    result = []
    for s in all_skills:
        meta = loader._get_skill_meta(s["name"])
        desc = loader._get_skill_description(s["name"])
        available = loader._check_requirements(meta)
        missing = loader._get_missing_requirements(meta) if not available else None
        result.append({
            "name": s["name"],
            "source": s["source"],
            "path": s["path"],
            "description": desc,
            "available": available,
            "missingRequirements": missing,
        })
    result.sort(key=lambda x: (0 if x["available"] else 1, x["name"]))
    _result(req_id, {"skills": result})


def handle_skills_get(req_id: str, params: dict) -> None:
    name = params.get("name", "").strip()
    if not name:
        _error(req_id, "name is required")
        return

    loader = _get_skills_loader()
    content = loader.load_skill(name)
    if content is None:
        _error(req_id, f"Skill not found: {name}")
        return

    skill_info = None
    for s in loader.list_skills(filter_unavailable=False):
        if s["name"] == name:
            skill_info = s
            break

    meta = loader._get_skill_meta(name)
    available = loader._check_requirements(meta)
    missing = loader._get_missing_requirements(meta) if not available else None
    metadata = loader.get_skill_metadata(name)

    _result(req_id, {
        "name": name,
        "source": skill_info["source"] if skill_info else "unknown",
        "path": skill_info["path"] if skill_info else "",
        "description": loader._get_skill_description(name),
        "available": available,
        "missingRequirements": missing,
        "content": content,
        "metadata": metadata,
    })


# ---------------------------------------------------------------------------
# Files handlers
# ---------------------------------------------------------------------------

def _get_workspace_path() -> Path:
    config = _state.load_config()
    return config.workspace_path.resolve()


def _get_session_files_path(session_key: str | None) -> Path | None:
    """Get the session-level files directory, if session_key is provided.

    Matches the logic in AgentLoop._setup_tools() so that files.revert/files.diff/files.write
    resolve relative paths to the same directory as the Agent's WriteFileTool/EditFileTool.
    """
    if not session_key:
        return None
    from miqi.utils.helpers import safe_filename  # noqa: PLC0415
    config = _state.load_config()
    safe_key = safe_filename(session_key.replace(":", "_"))
    files_dir = config.workspace_path / "sessions" / safe_key / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    return files_dir


def _validate_file_path(file_path: str, session_key: str | None = None) -> Path:
    """Resolve a relative path against workspace and block traversal.

    If session_key is provided and the session's workspace is enabled,
    resolves relative paths against the session-level files directory
    instead of the workspace root, matching AgentLoop._setup_tools().
    """
    workspace = _get_workspace_path()
    if not file_path or file_path.startswith("/") or file_path.startswith("\\"):
        raise ValueError("Only relative paths are allowed")

    # If we have a session_key, try session-level files dir first
    session_files = _get_session_files_path(session_key)
    if session_files:
        resolved = (session_files / file_path).resolve()
        if str(resolved).startswith(str(workspace) + str(Path("/"))) or resolved == workspace:
            return resolved

    # Fall back to workspace root
    resolved = (workspace / file_path).resolve()
    if not str(resolved).startswith(str(workspace) + str(Path("/"))) and resolved != workspace:
        raise ValueError(f"Path escapes workspace: {file_path}")
    return resolved


def _build_tree(path: Path, relative_to: Path, depth: int = 0, max_depth: int = 6) -> dict:
    """Build a FileNode tree for a directory."""
    node: dict[str, Any] = {
        "name": path.name or str(path),
        "path": str(path.relative_to(relative_to)).replace("\\", "/"),
        "is_dir": path.is_dir(),
    }
    if path.is_dir() and depth < max_depth:
        children = []
        _TREE_SKIP_SUFFIXES = {
            ".sqlite", ".sqlite-shm", ".sqlite-wal", ".sqlite-journal",
            ".db", ".db-shm", ".db-wal",
            ".pyc", ".pyo", ".pyd",
            ".so", ".dll", ".dylib", ".exe",
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp",
            ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
            ".bin", ".dat", ".pkl", ".npz", ".npy", ".h5", ".hdf5",
        }
        try:
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if child.name.startswith(".") or child.name == "__pycache__":
                    continue
                if child.suffix.lower() in _TREE_SKIP_SUFFIXES:
                    continue
                children.append(_build_tree(child, relative_to, depth + 1, max_depth))
        except PermissionError:
            pass
        node["children"] = children
    return node


def handle_files_tree(req_id: str, params: dict) -> None:
    workspace = _get_workspace_path()
    if not workspace.exists():
        _result(req_id, {"root": {"name": workspace.name, "path": ".", "is_dir": True, "children": []}, "workspace_path": str(workspace)})
        return
    root = _build_tree(workspace, workspace)
    _result(req_id, {"root": root, "workspace_path": str(workspace)})


def handle_files_read(req_id: str, params: dict) -> None:
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")
    _log(f"[files:read] req={req_id} path={file_path} session_key={session_key}")
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_file_path(file_path, session_key)
    except ValueError as exc:
        _log(f"[files:read] path validation failed: {exc}")
        _error(req_id, str(exc))
        return

    if not resolved.exists():
        _log(f"[files:read] not found: {file_path}")
        _error(req_id, f"File not found: {file_path}")
        return

    if resolved.is_dir():
        _log(f"[files:read] is directory: {file_path}")
        _error(req_id, f"Path is a directory: {file_path}")
        return

    # Only allow text-like files
    allowed = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
               ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".xml", ".svg",
               ".sh", ".bash", ".zsh", ".ps1", ".bat",
               ".env", ".gitignore", ".dockerignore", ".editorconfig",
               ".csv", ".log", ".lock", ".jsonl"}
    if resolved.suffix not in allowed and resolved.name not in {".gitignore", ".dockerignore", ".editorconfig", ".env"}:
        _log(f"[files:read] unsupported type: {resolved.suffix or resolved.name}")
        _error(req_id, f"File type not supported: {resolved.suffix or resolved.name}")
        return

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _log(f"[files:read] decode error: {file_path}")
        _error(req_id, "File is not valid UTF-8 text")
        return
    except Exception as exc:
        _log(f"[files:read] read error: {exc}")
        _error(req_id, str(exc))
        return

    _log(f"[files:read] ok path={file_path} size={len(content)}")
    _result(req_id, {
        "path": file_path,
        "content": content,
        "size": len(content),
    })


def handle_files_write(req_id: str, params: dict) -> None:
    file_path = params.get("path", "").strip()
    content = params.get("content", "")
    _log(f"[files:write] req={req_id} path={file_path} size={len(content)}")
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_file_path(file_path, session_key)
    except ValueError as exc:
        _log(f"[files:write] path validation failed: {exc}")
        _error(req_id, str(exc))
        return

    # Only allow text-like files for write
    allowed = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
               ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".xml", ".svg",
               ".sh", ".bash", ".zsh", ".ps1", ".bat",
               ".env", ".gitignore", ".dockerignore", ".editorconfig",
               ".csv", ".log", ".lock", ".jsonl"}
    if resolved.suffix not in allowed and resolved.name not in {".gitignore", ".dockerignore", ".editorconfig", ".env"}:
        _log(f"[files:write] unsupported file type: {resolved.suffix or resolved.name}")
        _error(req_id, f"File type not supported for write: {resolved.suffix or resolved.name}")
        return

    # Snapshot original content before first write (enables non-git diff/revert)
    session_key = params.get("session_key")
    snapshot_dir = _get_snapshot_dir_for_session(session_key)
    _maybe_snapshot(resolved, snapshot_dir=snapshot_dir)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved.write_text(content, encoding="utf-8")
        _log(f"[files:write] ok path={file_path}")
    except Exception as exc:
        _log(f"[files:write] write failed: {exc}")
        _error(req_id, str(exc))
        return
    _result(req_id, {"saved": True, "path": file_path})


def handle_files_delete(req_id: str, params: dict) -> None:
    """Delete a workspace file or empty directory."""
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")
    _log(f"[files:delete] req={req_id} path={file_path} session_key={session_key}")
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_file_path(file_path, session_key)
    except ValueError as exc:
        _log(f"[files:delete] path validation failed: {exc}")
        _error(req_id, str(exc))
        return

    if not resolved.exists():
        _log(f"[files:delete] not found: {file_path}")
        _error(req_id, f"Not found: {file_path}")
        return

    workspace = _get_workspace_path()
    if resolved == workspace:
        _log(f"[files:delete] refused: workspace root")
        _error(req_id, "Cannot delete workspace root")
        return

    if resolved.is_dir():
        if any(resolved.iterdir()):
            _log(f"[files:delete] not empty: {file_path}")
            _error(req_id, "Directory is not empty")
            return
        resolved.rmdir()
    else:
        resolved.unlink()

    _log(f"[files:delete] ok path={file_path}")
    _result(req_id, {"deleted": True, "path": file_path})


def _get_snapshot_dir_for_session(session_key: str | None) -> Path | None:
    """Get the session-level snapshot directory, if session_key is provided.

    Matches the logic in AgentLoop._setup_tools() so that files.revert/files.diff
    use the same snapshot directory as the Agent's WriteFileTool/EditFileTool.
    """
    if not session_key:
        return None
    from miqi.utils.helpers import safe_filename  # noqa: PLC0415
    config = _state.load_config()
    safe_key = safe_filename(session_key.replace(":", "_"))
    snap_dir = config.workspace_path / "sessions" / safe_key / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    return snap_dir


def handle_files_diff(req_id: str, params: dict) -> None:
    """Diff a file against its pre-session snapshot using difflib (no git required).

    For new files (no snapshot exists but file currently exists), generates a diff
    showing all content as additions (like 'git diff' for untracked files).
    """
    import difflib

    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")
    _log(f"[files:diff] req={req_id} path={file_path} session_key={session_key}")
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_file_path(file_path, session_key)
    except ValueError as exc:
        _log(f"[files:diff] path validation failed: {exc}")
        _error(req_id, str(exc))
        return

    snapshot_key = str(resolved)
    snapshot_dir = _get_snapshot_dir_for_session(session_key)
    with _snapshots_lock:
        original_content: str | None = _read_snapshot(snapshot_key, snapshot_dir=snapshot_dir)

    # Fall back to global snapshots dir
    if original_content is None:
        original_content = _read_snapshot(snapshot_key)

    # Read current content
    current_content: str | None = None
    file_exists = resolved.exists()
    if file_exists:
        try:
            current_content = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            _log(f"[files:diff] read current failed: {exc}")

    # If no snapshot exists, generate a diff showing all content as additions (new file)
    if original_content is None:
        if file_exists and current_content is not None and current_content != "":
            _log(f"[files:diff] new file detected for {snapshot_key}, generating full diff")
            # Generate diff showing all lines as additions (simulating git diff for untracked file)
            current_lines = current_content.splitlines(keepends=True)
            # Build unified diff header for new file
            diff_lines = [
                f"--- /dev/null",
                f"+++ b/{file_path}",
            ]
            # Add hunk header and all content as additions
            line_count = len(current_lines)
            diff_lines.append(f"@@ -0,0 +1,{line_count} @@")
            diff_lines.extend("+" + line for line in current_lines)
            diff_text = "\n".join(diff_lines)
            _result(req_id, {
                "path": file_path,
                "diff": diff_text,
                "has_diff": True,
                "original_content": None,
                "current_content": current_content,
                "is_new_file": True,
            })
            return
        _log(f"[files:diff] no snapshot for {snapshot_key}")
        _result(req_id, {
            "path": file_path,
            "diff": None,
            "has_diff": False,
            "original_content": None,
            "current_content": current_content,
            "error": "No snapshot found — file was not modified in this session",
        })
        return

    # Generate unified diff for modified files
    original_lines = original_content.splitlines(keepends=True)
    current_lines = (current_content or "").splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        original_lines,
        current_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    ))
    diff_text = "\n".join(diff_lines) if diff_lines else None
    has_diff = bool(diff_text)
    _log(f"[files:diff] ok has_diff={has_diff} lines={len(diff_lines)} path={file_path}")

    _result(req_id, {
        "path": file_path,
        "diff": diff_text,
        "has_diff": has_diff,
        "original_content": original_content,
        "current_content": current_content,
    })


def handle_files_revert(req_id: str, params: dict) -> None:
    """Revert a file to its pre-session snapshot (no git required)."""
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")
    _log(f"[files:revert] req={req_id} path={file_path} session_key={session_key}")
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_file_path(file_path, session_key)
    except ValueError as exc:
        _log(f"[files:revert] path validation failed: {exc}")
        _error(req_id, str(exc))
        return

    snapshot_key = str(resolved)
    snapshot_dir = _get_snapshot_dir_for_session(session_key)
    with _snapshots_lock:
        has_snapshot = _read_snapshot(snapshot_key, snapshot_dir=snapshot_dir) is not None

    if not has_snapshot:
        # Also check global snapshots dir (snapshot may have been written there
        # if snapshot_dir was None during _maybe_snapshot)
        has_snapshot = _read_snapshot(snapshot_key) is not None
        if has_snapshot:
            snapshot_dir = None  # use global dir for restore/delete
            _log(f"[files:revert] found snapshot in global dir for {snapshot_key}")

    if not has_snapshot:
        _log(f"[files:revert] no snapshot for {snapshot_key}")
        _error(req_id, "No snapshot found — cannot revert (file was not modified in this session)")
        return

    ok = _restore_snapshot(resolved, snapshot_dir=snapshot_dir)
    if not ok:
        _log(f"[files:revert] restore failed for {snapshot_key}")
        _error(req_id, "Revert failed — could not write original content")
        return

    # Remove snapshot so the file is treated as clean again
    with _snapshots_lock:
        _delete_snapshot(snapshot_key, snapshot_dir=snapshot_dir)

    _log(f"[files:revert] ok path={file_path}")
    # Remove tracked file entry from tracked_files.json
    if session_key:
        _remove_tracked_file(session_key, file_path)

    _result(req_id, {"reverted": True, "path": file_path})


def _get_session_manager():
    """Get a SessionManager for the current workspace."""
    from miqi.session.manager import SessionManager
    config = _state.load_config()
    return SessionManager(config.workspace_path)


def _reset_tracked_file_op(session_key: str, file_path: str) -> None:
    """Reset a tracked file entry's op to 'read' instead of removing it."""
    try:
        sm = _get_session_manager()
        sm.reset_tracked_file_op(session_key, file_path, op="read")
    except Exception as exc:
        _log(f"[files] reset_tracked_file_op failed: {exc}")


def handle_files_accept(req_id: str, params: dict) -> None:
    """Accept all changes for a file — keep current content, delete its snapshot."""
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")
    if not file_path:
        _error(req_id, "path is required")
        return

    _log(f"[files:accept] req={req_id} path={file_path} session_key={session_key}")

    # Reset tracked file entry to 'read' (keep it in the list, just clear mod status)
    if session_key:
        _reset_tracked_file_op(session_key, file_path)

    try:
        resolved = _validate_file_path(file_path, session_key)
    except ValueError as exc:
        _log(f"[files:accept] path validation failed: {exc}")
        _result(req_id, {"accepted": True, "path": file_path})
        return

    snapshot_key = str(resolved)
    snapshot_dir = _get_snapshot_dir_for_session(session_key)

    # Delete snapshot from session dir
    with _snapshots_lock:
        _delete_snapshot(snapshot_key, snapshot_dir=snapshot_dir)

    # Also clean global dir if snapshot landed there
    with _snapshots_lock:
        _delete_snapshot(snapshot_key)

    _log(f"[files:accept] ok path={file_path}")
    _result(req_id, {"accepted": True, "path": file_path})


def handle_skills_open_folder(req_id: str, params: dict) -> None:
    """Open the skill's containing folder in the system file manager."""
    name = params.get("name", "").strip()
    if not name:
        _error(req_id, "name is required")
        return

    loader = _get_skills_loader()
    skill_path = loader.get_skill_path(name)
    if skill_path is None:
        _error(req_id, f"Skill not found: {name}")
        return

    import subprocess
    import sys as _sys

    folder = str(skill_path.parent if skill_path.is_file() else skill_path)
    try:
        if _sys.platform == "win32":
            subprocess.run(["explorer", folder], check=False)
        elif _sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)
        _result(req_id, {"opened": True, "path": folder})
    except Exception as exc:
        _error(req_id, f"Failed to open folder: {exc}")


_SKILL_NAME_RE = re.compile(r'^[a-z][a-z0-9-]*$')


def handle_skills_create(req_id: str, params: dict) -> None:
    """Create a blank workspace skill."""
    name = str(params.get("name", "")).strip()
    description = str(params.get("description", "")).strip()
    if not name or not _SKILL_NAME_RE.match(name):
        _error(req_id, "Invalid name — use lowercase letters, digits, hyphens")
        return
    config = _state.load_config()
    skill_dir = config.workspace_path / "skills" / name
    if skill_dir.exists():
        _error(req_id, f"Skill '{name}' already exists")
        return
    skill_dir.mkdir(parents=True)
    template = (
        f"---\n"
        f"name: {name}\n"
        f"description: {description or 'A new skill'}\n"
        f"version: \"1.0\"\n"
        f"---\n\n"
        f"# {name}\n\n{description or 'A new skill'}\n"
    )
    (skill_dir / "SKILL.md").write_text(template, encoding="utf-8")
    _result(req_id, {"ok": True, "path": str(skill_dir)})


def handle_skills_upload(req_id: str, params: dict) -> None:
    """Save uploaded YAML content as a new workspace skill."""
    name = str(params.get("name", "")).strip()
    content = str(params.get("content", "")).strip()
    if not name or not content:
        _error(req_id, "name and content are required")
        return
    config = _state.load_config()
    skill_dir = config.workspace_path / "skills" / name
    if skill_dir.exists():
        _error(req_id, f"Skill '{name}' already exists")
        return
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    _result(req_id, {"ok": True})


def handle_skills_delete(req_id: str, params: dict) -> None:
    """Delete a workspace skill. Builtin skills cannot be deleted."""
    name = str(params.get("name", "")).strip()
    import shutil as _shutil

    builtin_dir = Path(__file__).parent.parent / "skills"
    if (builtin_dir / name).exists():
        _error(req_id, "Builtin skills cannot be deleted")
        return
    config = _state.load_config()
    skill_dir = config.workspace_path / "skills" / name
    if not skill_dir.exists():
        _error(req_id, f"Skill '{name}' not found in workspace")
        return
    _shutil.rmtree(skill_dir)
    _result(req_id, {"ok": True})


def handle_mcp_list(req_id: str, params: dict) -> None:
    """List all configured MCP servers."""
    config = _state.load_config()
    servers = config.tools.mcp_servers or {}
    _result(req_id, {
        "servers": [
            {"name": name, **srv.model_dump()}
            for name, srv in servers.items()
        ]
    })


def handle_mcp_upsert(req_id: str, params: dict) -> None:
    """Create or update an MCP server entry by name."""
    from miqi.config.schema import MCPServerConfig
    from miqi.config.loader import save_config

    name = str(params.pop("name", "")).strip()
    if not name:
        _error(req_id, "name is required")
        return
    try:
        server_cfg = MCPServerConfig(**params)
    except Exception as exc:
        _error(req_id, str(exc))
        return
    config = _state.load_config()
    if config.tools.mcp_servers is None:
        config.tools.mcp_servers = {}
    config.tools.mcp_servers[name] = server_cfg
    save_config(config)
    _state.config = config
    _result(req_id, {"ok": True})


def handle_mcp_delete(req_id: str, params: dict) -> None:
    """Remove an MCP server entry by name."""
    from miqi.config.loader import save_config

    name = str(params.get("name", "")).strip()
    config = _state.load_config()
    if config.tools.mcp_servers and name in config.tools.mcp_servers:
        del config.tools.mcp_servers[name]
        save_config(config)
        _state.config = config
    _result(req_id, {"ok": True})


def handle_python_check(req_id: str, params: dict) -> None:
    """Check if Python and MiQi are available."""
    import importlib

    issues = []

    # Check Python version
    py_ver = sys.version_info
    if py_ver < (3, 11):
        issues.append(f"Python {py_ver.major}.{py_ver.minor} is too old (need >= 3.11)")

    # Check key dependencies
    for mod in ("pydantic", "httpx", "loguru"):
        try:
            importlib.import_module(mod)
        except ImportError:
            issues.append(f"Missing dependency: {mod}")

    _result(req_id, {
        "ok": len(issues) == 0,
        "python_version": f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}",
        "issues": issues,
        "config_exists": (Path.home() / ".miqi" / "config.json").exists(),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET_FIELDS = {"apiKey", "api_key", "token", "secret", "password", "appSecret"}


def _redact_secrets(obj: Any, parent_key: str = "") -> None:
    """Redact secret values in-place."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _SECRET_FIELDS or any(s in k.lower() for s in ("secret", "token", "password", "api_key", "apikey")):
                if isinstance(v, str) and v:
                    obj[k] = v[:4] + "****" if len(v) > 4 else "****"
            elif isinstance(v, (dict, list)):
                _redact_secrets(v, k)
    elif isinstance(obj, list):
        for item in obj:
            _redact_secrets(item, parent_key)


def _deep_merge(base: dict, updates: dict) -> dict:
    """Deep merge updates into base, returning a new dict."""
    result = base.copy()
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

_METHODS = {
    "status": handle_status,
    "chat.send": handle_chat_send,
    "chat.abort": handle_chat_abort,
    "sessions.list": handle_sessions_list,
    "sessions.get": handle_sessions_get,
    "sessions.delete": handle_sessions_delete,
    "sessions.archive": handle_sessions_archive,
    "sessions.unarchive": handle_sessions_unarchive,
    "sessions.list_archived": handle_sessions_list_archived,
    "sessions.get_tracked_files": handle_sessions_get_tracked_files,
    "sessions.clear_tracked_files": handle_sessions_clear_tracked_files,
    "config.get": handle_config_get,
    "config.update": handle_config_update,
    "providers.list": handle_providers_list,
    "providers.test": handle_providers_test,
    "providers.update": handle_providers_update,
    "channels.list": handle_channels_list,
    "channels.update": handle_channels_update,
    "approvals.list": handle_approvals_list,
    "approvals.resolve": handle_approvals_resolve,
    "approvals.clear_permanent": handle_approvals_clear_permanent,
    "approvals.add_permanent": handle_approvals_add_permanent,
    "approvals.history": handle_approvals_history,
    "cron.list": handle_cron_list,
    "cron.create": handle_cron_create,
    "cron.update": handle_cron_update,
    "cron.delete": handle_cron_delete,
    "cron.toggle": handle_cron_toggle,
    "cron.run": handle_cron_run,
    "cron.runs": handle_cron_runs,
    "memory.list": handle_memory_list,
    "memory.get": handle_memory_get,
    "memory.update": handle_memory_update,
    "memory.delete": handle_memory_delete,
    "memory.lessons": handle_memory_lessons,
    "memory.lesson.unlearn": handle_memory_lesson_unlearn,
    "experience:list":   handle_experience_list,
    "experience:delete": handle_experience_delete,
    "experience:toggle": handle_experience_toggle,
    "experience:search": handle_experience_search,
    "skills.list": handle_skills_list,
    "skills.get": handle_skills_get,
    "skills.open_folder": handle_skills_open_folder,
    "skills.create": handle_skills_create,
    "skills.upload": handle_skills_upload,
    "skills.delete": handle_skills_delete,
    "mcp.list": handle_mcp_list,
    "mcp.upsert": handle_mcp_upsert,
    "mcp.delete": handle_mcp_delete,
    "files.tree": handle_files_tree,
    "files.read": handle_files_read,
    "files.write": handle_files_write,
    "files.delete": handle_files_delete,
    "files.diff": handle_files_diff,
    "files.revert": handle_files_revert,
    "files.accept": handle_files_accept,
    "python.check": handle_python_check,
}


def _dispatch(req_id: str, method: str, params: dict) -> None:
    handler = _METHODS.get(method)
    if handler is None:
        _error(req_id, f"Unknown method: {method}")
        return
    handler(req_id, params)


def _ensure_workspace_init() -> None:
    """Create workspace directories and template files if they don't exist."""
    try:
        from importlib.resources import files as pkg_files

        from miqi.utils.helpers import get_workspace_path

        workspace = get_workspace_path()
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "memory").mkdir(exist_ok=True)
        (workspace / "skills").mkdir(exist_ok=True)

        templates_dir = pkg_files("miqi") / "templates"
        for item in templates_dir.iterdir():
            if not item.name.endswith(".md"):
                continue
            dest = workspace / item.name
            if not dest.exists():
                dest.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")

        memory_template = templates_dir / "memory" / "MEMORY.md"
        memory_file = workspace / "memory" / "MEMORY.md"
        if not memory_file.exists():
            memory_file.write_text(memory_template.read_text(encoding="utf-8"), encoding="utf-8")

        _log("Workspace ready")
    except Exception as exc:
        _log(f"Workspace init warning (non-fatal): {exc}")


# Global bridge state — accessible from atexit/signal handlers
_bridge_state: BridgeState | None = None


def _graceful_shutdown() -> None:
    """Attempt to destroy all sandboxes on shutdown.

    Called via atexit or signal handler. Uses a sync wrapper around
    the async destroy_all() since we can't await in these contexts.
    """
    global _bridge_state
    if _bridge_state is None:
        return

    sandbox_mgr = getattr(_bridge_state, "_sandbox_manager", None)
    if sandbox_mgr is None or sandbox_mgr == "disabled":
        return

    # Try async destroy — run in a new event loop if needed
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside a running loop — schedule the cleanup
            asyncio.ensure_future(sandbox_mgr.destroy_all())
        else:
            # No running loop — create one
            asyncio.run(sandbox_mgr.destroy_all())
    except Exception as exc:
        _log(f"Sandbox cleanup on shutdown failed (non-fatal): {exc}")
    finally:
        # Always clear the state file to prevent stale entries
        try:
            sandbox_mgr._clear_state_file()
        except Exception:
            pass
        _bridge_state = None


def main() -> None:
    global _bridge_state
    _init_logging()
    _log("Bridge server starting")
    _ensure_workspace_init()
    # Persist approval history so records survive bridge restarts
    try:
        from miqi.agent.command_approval import init_history_file
        from miqi.config.loader import get_data_dir
        init_history_file(get_data_dir() / "approval_history.jsonl")
    except Exception as exc:
        _log(f"Approval history init warning (non-fatal): {exc}")

    # Initialize bridge state — reuse the global _state instance
    _bridge_state = _state

    # Register graceful shutdown: destroy sandboxes & clear state file
    atexit.register(_graceful_shutdown)

    # Also handle SIGTERM (e.g. from Electron's process.kill() or Hot Reload)
    try:
        signal.signal(signal.SIGTERM, lambda *_: _graceful_shutdown())
    except (OSError, ValueError):
        # signal.signal can fail if not in main thread or not supported
        pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            _dispatch(req["id"], req["method"], req.get("params", {}))
        except json.JSONDecodeError as exc:
            _log(f"Invalid JSON: {exc}")
        except Exception:
            _log(f"Unhandled error: {traceback.format_exc()}")
            try:
                _error(req.get("id", "?"), "Internal bridge error")
            except Exception:
                pass

    # stdin closed — graceful exit
    _graceful_shutdown()
    _log("Bridge server stopped")


if __name__ == "__main__":
    main()
