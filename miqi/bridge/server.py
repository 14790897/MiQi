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
import traceback
from pathlib import Path
from typing import Any


def _log(msg: str) -> None:
    print(f"[miqi-bridge] {msg}", file=sys.stderr, flush=True)


def _send(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(req_id: str, result: Any = None) -> None:
    _send({"id": req_id, "result": result if result is not None else {}})


def _error(req_id: str, message: str) -> None:
    _send({"id": req_id, "error": message})


def _event(req_id: str, event_type: str, data: Any) -> None:
    _send({"id": req_id, "type": event_type, "data": data})


# ---------------------------------------------------------------------------
# Bridge state
# ---------------------------------------------------------------------------

class BridgeState:
    """Holds cached config and agent loops across requests."""

    def __init__(self) -> None:
        self.config = None  # lazy-loaded

    def load_config(self):
        from miqi.config.loader import load_config

        self.config = load_config()
        return self.config

    def build_agent(self, session_key: str):
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
        )
        return agent


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

    async def _run() -> None:
        agent = _state.build_agent(session_key)

        async def on_progress(text: str, tool_hint: bool = False) -> None:
            _event(req_id, "progress", {"text": text, "tool_hint": tool_hint})

        result = await agent.process_direct(
            content=content,
            session_key=session_key,
            channel="desktop",
            chat_id=session_key,
            on_progress=on_progress,
        )
        _event(req_id, "final", {"content": result})

    try:
        asyncio.run(_run())
    except Exception as exc:
        _log(f"chat.send error: {exc}")
        _event(req_id, "error", {"message": str(exc)})


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
    api_key = params.get("api_key", "")
    api_base = params.get("api_base") or None

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
    "sessions.list": handle_sessions_list,
    "sessions.get": handle_sessions_get,
    "sessions.delete": handle_sessions_delete,
    "config.get": handle_config_get,
    "config.update": handle_config_update,
    "providers.list": handle_providers_list,
    "providers.test": handle_providers_test,
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
