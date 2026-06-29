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
    """Holds cached config, abort state, and shared sandbox manager."""

    def __init__(self) -> None:
        self.config = None  # lazy-loaded
        self._lock = threading.Lock()
        self._terminated: set[str] = set()
        self._pending_approvals: dict[str, threading.Event] = {}
        self._approval_decisions: dict[str, str] = {}
        self._approval_meta: dict[str, dict] = {}
        self._sandbox_manager: Any = None  # shared SandboxManager across agents
        self._event_emitter: Any = None  # Phase 1 shared EventEmitter
        self._agent_control: Any = None  # Phase 2 shared AgentControl
        self._orchestrator: Any = None  # Phase 3 shared ToolOrchestrator
        self._plan_tracker: Any = None  # Phase 9 shared PlanTracker
        self._plugin_manager: Any = None  # Phase 4 shared PluginManager
        self._runtime_sessions: dict[str, Any] = {}  # Phase 11 RuntimeSession cache

    def load_config(self):
        from miqi.config.loader import load_config

        self.config = load_config()
        return self.config

    async def get_runtime_session(self, session_key: str, *, caller_id: str = "", approval_callback=None):
        """Get or create a RuntimeSession for the given session key.

        Sessions are cached and reused across bridge requests. This is the
        Phase 11 foundation — actual chat routing through RuntimeSession
        will happen in Phase 14.

        Session keys are namespaced per caller to prevent cross-user
        session access when multiple frontends share a bridge process.
        caller_id will become REQUIRED in Phase 14 (no default).
        """
        import warnings

        if not caller_id:
            warnings.warn(
                "get_runtime_session called without caller_id — "
                "sessions are NOT isolated. caller_id will be required "
                "in Phase 14.",
                FutureWarning,
                stacklevel=2,
            )

        from miqi.providers.factory import make_provider
        from miqi.runtime.session import RuntimeSession

        # Namespace sessions by caller to prevent cross-user access
        ns_key = f"{caller_id}:{session_key}" if caller_id else session_key

        runtime = self._runtime_sessions.get(ns_key)
        if runtime is not None:
            return runtime

        config = self.load_config()
        provider = make_provider(config)
        runtime = RuntimeSession.create(
            config=config,
            provider=provider,
            session_id=ns_key,
            workspace=config.workspace_path,
        )
        await runtime.start()
        self._runtime_sessions[ns_key] = runtime
        return runtime

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

    def destroy_sandbox(self, session_key: str, *, client_id: str | None = None) -> bool:
        """Destroy the sandbox for a session (called on delete/archive).

        Phase 30: client_id is used to compute the client-scoped sandbox key.
        When client_id is None, falls back to raw session_key (legacy path).
        """
        if self._sandbox_manager is None or self._sandbox_manager == "disabled":
            return False
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    self._sandbox_manager.destroy(session_key, client_id=client_id),
                )
            finally:
                loop.close()
            return result
        except Exception as exc:
            _log(f"destroy_sandbox error: {exc}")
            return False

    def abort_active(self) -> dict:
        """Resolve all pending approvals so blocked daemon threads can exit.

        After Phase 14, turn abort is handled by RuntimeSession.submit(AbortTurn(...)).
        This method remains as a safety net to unblock approval-waiting threads
        (the user-facing abort button also calls RuntimeSession, not this method).
        """
        pending_ids = self.list_pending_approval_ids()
        for aid in pending_ids:
            self.resolve_approval(aid, "deny")
        return {"aborted": len(pending_ids) > 0}

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
    from miqi.paths import get_config_path
    config_exists = get_config_path()
    _result(req_id, {
        "status": "ok",
        "configured": config_exists.exists(),
        "python_version": sys.version,
    })


# Phase 27.3: handle_chat_send, _run_chat_send_via_runtime, handle_chat_abort,
# and _caller_id_from_params removed. chat.send routes through
# BridgeRuntimeLoop._chat_send_handler → AppServer → RuntimeSession.
# chat.abort routes through AppServer (registered by register_command_handlers).


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


def _get_session_manager():
    """Get a SessionManager instance for the current workspace."""
    config = _state.load_config()
    from miqi.session.manager import SessionManager
    return SessionManager(config.workspace_path)


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
        from miqi.cron.service import _validate_schedule_for_add

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
    # Must be within the memory directory — use relative_to for robust containment
    try:
        resolved.relative_to(memory_dir.resolve())
    except ValueError:
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
    from miqi.paths import get_config_path

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
        "config_exists": get_config_path().exists(),
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
# Permissions handlers (Phase 3)
# ---------------------------------------------------------------------------


def handle_permissions_get(req_id: str, params: dict) -> None:
    """Return current permission engine configuration."""
    orch = _state._orchestrator
    if orch is not None:
        pe = orch.permissions
        _result(req_id, {
            "filesystem": {"rules": [], "default_mode": "read"},
            "network": "allow_all",
            "exec_approval": "dangerous",
            "permanent_allowlist": list(pe.permanent_allowlist),
            "deny_patterns": list(pe.deny_patterns),
        })
    else:
        _result(req_id, {
            "filesystem": {"rules": [], "default_mode": "read"},
            "network": "allow_all",
            "exec_approval": "dangerous",
            "permanent_allowlist": [],
            "deny_patterns": [],
        })


def handle_permissions_update(req_id: str, params: dict) -> None:
    """Update permission engine deny/allow patterns."""
    config = params.get("config", {})
    orch = _state._orchestrator
    if orch is not None:
        pe = orch.permissions
        if "permanent_allowlist" in config:
            pe.permanent_allowlist = set(config["permanent_allowlist"])
        if "deny_patterns" in config:
            pe.deny_patterns = set(config["deny_patterns"])
    _result(req_id, {"saved": True})


def handle_permissions_permanent_add(req_id: str, params: dict) -> None:
    """Add a pattern to the permanent allowlist."""
    pattern = params.get("pattern", "")
    orch = _state._orchestrator
    if orch is not None and pattern:
        orch.permissions.permanent_allowlist.add(pattern)
    _result(req_id, {"added": bool(pattern)})


def handle_permissions_permanent_remove(req_id: str, params: dict) -> None:
    """Remove a pattern from the permanent allowlist."""
    pattern = params.get("pattern", "")
    orch = _state._orchestrator
    if orch is not None and pattern:
        orch.permissions.permanent_allowlist.discard(pattern)
    _result(req_id, {"removed": bool(pattern)})


# ---------------------------------------------------------------------------
# Plugin handlers (Phase 4)
# ---------------------------------------------------------------------------


def handle_plugins_list(req_id: str, params: dict) -> None:
    """List installed plugins."""
    pm = getattr(_state, '_plugin_manager', None)
    if pm is None:
        _result(req_id, {"plugins": []})
        return
    plugins = []
    for p in pm.list_plugins():
        plugins.append({
            "name": p.manifest.name,
            "version": p.manifest.version,
            "description": p.manifest.description,
            "author": p.manifest.author,
            "scope": p.scope,
            "status": p.status,
            "error": p.error,
            "mcp_servers": p.manifest.mcp_servers,
            "skills": p.manifest.skills,
            "slash_commands": p.manifest.slash_commands,
        })
    _result(req_id, {"plugins": plugins})


def handle_plugins_install(req_id: str, params: dict) -> None:
    """Install a plugin from a GitHub URL or local path."""
    name = params.get("name", "")
    url = params.get("url", "")
    pm = getattr(_state, '_plugin_manager', None)
    if pm is None:
        _result(req_id, {"ok": False, "error": "Plugin manager not initialized"})
        return

    # Validate plugin name: no path separators, no traversal, no '..'
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$', name):
        _result(req_id, {"ok": False, "error": "Invalid plugin name"})
        return
    if ".." in name:
        _result(req_id, {"ok": False, "error": "Invalid plugin name"})
        return

    import subprocess
    import shutil
    target_dir = (pm.user_dir / name).resolve()
    # Ensure resolved path stays within the plugins directory — use relative_to for robust containment
    try:
        target_dir.relative_to(pm.user_dir.resolve())
    except ValueError:
        _result(req_id, {"ok": False, "error": "Invalid plugin path"})
        return
    if target_dir.exists():
        _result(req_id, {"ok": False, "error": f"Plugin '{name}' already installed"})
        return

    try:
        if url:
            # Validate URL: HTTPS only, known hosts only
            from urllib.parse import urlparse
            parsed = urlparse(url)
            ALLOWED_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
            if parsed.scheme != "https":
                _result(req_id, {"ok": False, "error": "Only HTTPS URLs are supported"})
                return
            if parsed.hostname not in ALLOWED_HOSTS:
                _result(req_id, {"ok": False, "error": f"Unsupported host: {parsed.hostname}"})
                return
            # Prevent credential injection in URL
            if "@" in parsed.netloc:
                _result(req_id, {"ok": False, "error": "Credentials in URL are not allowed"})
                return

            subprocess.run(
                ["git", "clone", "--depth=1", "--", url, str(target_dir)],
                check=True, capture_output=True, text=True, timeout=60,
            )
            # Reload plugins (safe async call from sync handler)
            from miqi.utils.async_utils import run_async_safely
            run_async_safely(pm.discover())
            # Update MCP servers from newly installed plugin
            new_servers = pm.get_mcp_servers()
            if new_servers and hasattr(_state, '_mcp_servers'):
                _state._mcp_servers.update({s.get("name", ""): s for s in new_servers})
            _result(req_id, {"ok": True, "name": name})
        else:
            _result(req_id, {"ok": False, "error": "url is required for plugin installation"})
    except subprocess.CalledProcessError as e:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        _result(req_id, {"ok": False, "error": f"Clone failed: {e.stderr}"})
    except Exception as e:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        _result(req_id, {"ok": False, "error": str(e)})


def handle_plugins_uninstall(req_id: str, params: dict) -> None:
    """Uninstall a plugin by name."""
    name = params.get("name", "")
    pm = getattr(_state, '_plugin_manager', None)
    if pm is None:
        _result(req_id, {"ok": False, "error": "Plugin manager not initialized"})
        return

    # Validate plugin name: no path separators, no traversal
    import re as _re2
    if not _re2.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$', name):
        _result(req_id, {"ok": False, "error": "Invalid plugin name"})
        return
    if ".." in name:
        _result(req_id, {"ok": False, "error": "Invalid plugin name"})
        return

    import shutil
    for base in [pm.user_dir, pm.system_dir]:
        target = (base / name).resolve()
        base_resolved = base.resolve()
        # Ensure resolved path stays within the plugins directory — use relative_to for robust containment
        try:
            target.relative_to(base_resolved)
        except ValueError:
            continue
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            if name in pm._plugins:
                del pm._plugins[name]
            _result(req_id, {"ok": True, "name": name})
            return
    _result(req_id, {"ok": False, "error": f"Plugin '{name}' not found"})


def handle_plugins_toggle(req_id: str, params: dict) -> None:
    """Toggle a plugin enabled/disabled."""
    name = params.get("name", "")
    enabled = params.get("enabled", False)
    pm = getattr(_state, '_plugin_manager', None)
    if pm is None:
        _result(req_id, {"ok": False, "error": "Plugin manager not initialized"})
        return

    # Validate plugin name
    import re as _re3
    if not _re3.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$', name):
        _result(req_id, {"ok": False, "error": "Invalid plugin name"})
        return
    if ".." in name:
        _result(req_id, {"ok": False, "error": "Invalid plugin name"})
        return

    plugin = pm._plugins.get(name)
    if plugin is None:
        _result(req_id, {"ok": False, "error": f"Plugin '{name}' not found"})
        return
    plugin.status = "active" if enabled else "disabled"
    _result(req_id, {"ok": True, "name": name, "enabled": enabled})


# ---------------------------------------------------------------------------
# Agent + Plan handlers (Phase 2/3 bridge)
# ---------------------------------------------------------------------------


def handle_agent_list(req_id: str, params: dict) -> None:
    """List all agents and their status."""
    ac = _state._agent_control
    if ac is not None:
        agents = ac.list_agents()
        _result(req_id, {"agents": agents})
    else:
        _result(req_id, {"agents": []})


def handle_agent_get(req_id: str, params: dict) -> None:
    """Get detailed information about an agent."""
    ac = _state._agent_control
    if ac is None:
        _result(req_id, {"error": "Agent control not initialized"})
        return
    agent_id = params.get("agent_id", "")
    try:
        detail = ac.get_agent_detail(agent_id)
        _result(req_id, {"agent": detail})
    except KeyError:
        _result(req_id, {"error": f"Unknown agent: {agent_id}"})


# Phase 27.4: handle_agent_spawn and handle_agent_kill removed.
# agent.spawn and agent.kill now route through AppServer handlers
# registered by BridgeRuntimeLoop._init_app_server().


def handle_plan_get(req_id: str, params: dict) -> None:
    """Get current plan for a thread."""
    plan_id = params.get("plan_id", "")
    tracker = getattr(_state, '_plan_tracker', None)
    if tracker is not None and plan_id:
        plan = tracker.get(plan_id)
        if plan is not None:
            _result(req_id, {"plan": tracker.to_dict(plan)})
            return
    _result(req_id, {"plan": None})


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

_METHODS = {
    "status": handle_status,
    # chat.send and chat.abort are now AppServer methods (Phase 27.3)
    # sessions.* are now AppServer methods (Phase 28.4)
    # config.get/config.update are now AppServer methods (Phase 28.3)
    # providers.* are now AppServer methods (Phase 35.2)
    # channels.* are now AppServer methods (Phase 35.2)
    # approvals.* are now AppServer methods (Phase 28.2)
    # cron.* are now AppServer methods (Phase 35.6)
    # memory.* are now AppServer methods (Phase 35.7)
    # experience:* are now AppServer methods (Phase 35.7)
    # skills.* are now AppServer methods (Phase 35.5)
    # mcp.* are now AppServer methods (Phase 35.4)
    # python.check is now an AppServer method (Phase 35.8)
    # plugins.* are now AppServer methods (Phase 35.3)
    # permissions.* are now AppServer methods (Phase 35.2)
    # agent.* are now AppServer methods (Phases 27.4 + 28.5)
    "plan.get": handle_plan_get,
}


def _dispatch(req_id: str, method: str, params: dict) -> None:
    handler = _METHODS.get(method)
    if handler is None:
        _error(req_id, f"Unknown method: {method}")
        return
    handler(req_id, params)


# ── Phase 26: AppServer-backed dispatch ──────────────────────────────────

_app_server: Any = None  # lazily created AppServer


def _ensure_app_server() -> Any:
    """Return the AppServer instance created by BridgeRuntimeLoop.

    Phase 27.2: AppServer is now owned by BridgeRuntimeLoop
    (miqi/bridge/loop.py). This function returns the global
    reference for backward compatibility with tests.
    """
    global _app_server
    return _app_server


# Phase 27.2: _register_app_server_methods removed. Handler registration
# now happens in BridgeRuntimeLoop._init_app_server() in miqi/bridge/loop.py.
# Phase 27.1: _dispatch_via_appserver removed. All dispatch now goes through
# BridgeRuntimeLoop._drain_loop() which uses the persistent event loop.


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
            # Phase 27.6: persistent loop running — schedule cleanup
            asyncio.ensure_future(sandbox_mgr.destroy_all())
        else:
            # No running loop (signal/atexit after loop closed) — create one
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

    # Phase 27.1: use BridgeRuntimeLoop with persistent asyncio event loop
    # instead of per-request asyncio.run(). Legacy handlers continue to
    # work via the _dispatch fallback path.
    from miqi.bridge.loop import BridgeRuntimeLoop

    bridge = BridgeRuntimeLoop(
        send_func=_send,
        dispatch_legacy_func=_dispatch,
        bridge_state=_state,
        dev_mode=False,
    )
    bridge.start()

    # stdin closed — graceful exit
    _graceful_shutdown()
    _log("Bridge server stopped")


if __name__ == "__main__":
    main()
