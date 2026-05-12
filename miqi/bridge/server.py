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
import traceback
import uuid
from pathlib import Path
from typing import Any


_stdout_lock = threading.Lock()


def _log(msg: str) -> None:
    print(f"[miqi-bridge] {msg}", file=sys.stderr, flush=True)


def _send(data: dict[str, Any]) -> None:
    """Write one atomic JSON line to stdout (thread-safe)."""
    line = json.dumps(data, ensure_ascii=False) + "\n"
    with _stdout_lock:
        sys.stdout.write(line)
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

    def register_approval(self, approval_id: str) -> threading.Event:
        """Create and store an event for a pending approval. Returns the event."""
        evt = threading.Event()
        with self._lock:
            self._pending_approvals[approval_id] = evt
        return evt

    def resolve_approval(self, approval_id: str, decision: str) -> bool:
        """Set the decision and unblock the waiting callback. Returns True if found."""
        with self._lock:
            evt = self._pending_approvals.pop(approval_id, None)
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
                evt = _state.register_approval(approval_id)
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

    if not update:
        _error(req_id, "No fields to update")
        return

    current_dict = pc.model_dump(by_alias=False)
    current_dict.update(update)

    from miqi.config.schema import ProviderConfig
    new_pc = ProviderConfig.model_validate(current_dict)
    setattr(config.providers, provider_name, new_pc)
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
    from miqi.agent.command_approval import get_permanent_allowlist
    config = _state.load_config()
    pending_ids = _state.list_pending_approval_ids()
    _result(req_id, {
        "pending_ids": pending_ids,
        "permanent_allowlist": sorted(get_permanent_allowlist()),
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
    from miqi.agent.command_approval import _lock, _permanent_approved
    pattern = params.get("pattern")
    with _lock:
        if pattern:
            _permanent_approved.discard(pattern)
        else:
            _permanent_approved.clear()
    _result(req_id, {"cleared": True})


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
    "python.check": handle_python_check,
}


def _dispatch(req_id: str, method: str, params: dict) -> None:
    handler = _METHODS.get(method)
    if handler is None:
        _error(req_id, f"Unknown method: {method}")
        return
    handler(req_id, params)


def main() -> None:
    _log("Bridge server starting")
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
