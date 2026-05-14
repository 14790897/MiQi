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
import json
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


def _log(msg: str) -> None:
    print(f"[miqi-bridge] {msg}", file=sys.stderr, flush=True)


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
    """Holds cached config, active agent, and abort state."""

    def __init__(self) -> None:
        self.config = None  # lazy-loaded
        self._lock = threading.Lock()
        self._active_agent: Any = None
        self._active_req_id: str | None = None
        self._terminated: set[str] = set()
        self._pending_approvals: dict[str, threading.Event] = {}
        self._approval_decisions: dict[str, str] = {}
        self._approval_meta: dict[str, dict] = {}

    def load_config(self):
        from miqi.config.loader import load_config

        self.config = load_config()
        return self.config

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
        )
        return agent

    def set_active(self, agent: Any, req_id: str) -> None:
        with self._lock:
            self._active_agent = agent
            self._active_req_id = req_id

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
    _result(req_id, {"deleted": deleted})


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
    providers_out = []
    for spec in PROVIDERS:
        pc = getattr(config.providers, spec.name, None)
        providers_out.append({
            "name": spec.name,
            "display_name": spec.display_name or spec.name.title(),
            "env_key": spec.env_key,
            "provider_type": spec.provider_type,
            "is_gateway": spec.is_gateway,
            "is_local": spec.is_local,
            "default_api_base": spec.default_api_base,
            "configured": bool(pc and (pc.api_key or pc.api_base)),
            "api_base": pc.api_base if pc else None,
            "configured_model": config.agents.defaults.model,
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
        lesson_confidence_decay_hours=config.agents.self_improvement.lesson_confidence_decay_hours,
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
        lesson_confidence_decay_hours=config.agents.self_improvement.lesson_confidence_decay_hours,
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


def _validate_file_path(file_path: str) -> Path:
    """Resolve a relative path against workspace and block traversal."""
    workspace = _get_workspace_path()
    if not file_path or file_path.startswith("/") or file_path.startswith("\\"):
        raise ValueError("Only relative paths are allowed")
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
        try:
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if child.name.startswith(".") or child.name == "__pycache__":
                    continue
                if child.name.endswith(".pyc") or child.name.endswith(".pyo"):
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
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_file_path(file_path)
    except ValueError as exc:
        _error(req_id, str(exc))
        return

    if not resolved.exists():
        _error(req_id, f"File not found: {file_path}")
        return

    if resolved.is_dir():
        _error(req_id, f"Path is a directory: {file_path}")
        return

    # Only allow text-like files
    allowed = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
               ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".xml", ".svg",
               ".sh", ".bash", ".zsh", ".ps1", ".bat",
               ".env", ".gitignore", ".dockerignore", ".editorconfig",
               ".csv", ".log", ".lock", ".jsonl"}
    if resolved.suffix not in allowed and resolved.name not in {".gitignore", ".dockerignore", ".editorconfig", ".env"}:
        _error(req_id, f"File type not supported: {resolved.suffix or resolved.name}")
        return

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _error(req_id, "File is not valid UTF-8 text")
        return
    except Exception as exc:
        _error(req_id, str(exc))
        return

    _result(req_id, {
        "path": file_path,
        "content": content,
        "size": len(content),
    })


def handle_files_write(req_id: str, params: dict) -> None:
    file_path = params.get("path", "").strip()
    content = params.get("content", "")
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_file_path(file_path)
    except ValueError as exc:
        _error(req_id, str(exc))
        return

    # Only allow text-like files for write
    allowed = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
               ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".xml", ".svg",
               ".sh", ".bash", ".zsh", ".ps1", ".bat",
               ".env", ".gitignore", ".dockerignore", ".editorconfig",
               ".csv", ".log", ".lock", ".jsonl"}
    if resolved.suffix not in allowed and resolved.name not in {".gitignore", ".dockerignore", ".editorconfig", ".env"}:
        _error(req_id, f"File type not supported for write: {resolved.suffix or resolved.name}")
        return

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    _result(req_id, {"saved": True, "path": file_path})


def handle_files_delete(req_id: str, params: dict) -> None:
    """Delete a workspace file or empty directory."""
    file_path = params.get("path", "").strip()
    if not file_path:
        _error(req_id, "path is required")
        return

    try:
        resolved = _validate_file_path(file_path)
    except ValueError as exc:
        _error(req_id, str(exc))
        return

    if not resolved.exists():
        _error(req_id, f"Not found: {file_path}")
        return

    workspace = _get_workspace_path()
    if resolved == workspace:
        _error(req_id, "Cannot delete workspace root")
        return

    if resolved.is_dir():
        if any(resolved.iterdir()):
            _error(req_id, "Directory is not empty")
            return
        resolved.rmdir()
    else:
        resolved.unlink()

    _result(req_id, {"deleted": True, "path": file_path})


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
    "skills.list": handle_skills_list,
    "skills.get": handle_skills_get,
    "skills.open_folder": handle_skills_open_folder,
    "files.tree": handle_files_tree,
    "files.read": handle_files_read,
    "files.write": handle_files_write,
    "files.delete": handle_files_delete,
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


def main() -> None:
    _log("Bridge server starting")
    _ensure_workspace_init()
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
    _log("Bridge server stopped")


if __name__ == "__main__":
    main()
