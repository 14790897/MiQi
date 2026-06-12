"""AppServer — transport-agnostic protocol boundary and session registry.

Phase 26: Owns client→session mapping, method dispatch, middleware chain,
and event fanout. Transport adapters (DesktopBridge, CLI, TUI, Gateway)
call AppServer; they do NOT own business logic or session state.

Design principles:
- Transport-agnostic: no stdin/stdout/HTTP/WebSocket knowledge.
- client_id is the stable caller identity; session_id is the runtime scope.
- Middleware runs before handler dispatch (auth, rate-limit, logging).
- Error responses are sanitized — no internal paths or tracebacks to clients.
"""

from __future__ import annotations

import asyncio
import time
import uuid
import warnings
from pathlib import Path
from typing import Any, Callable, Coroutine

from loguru import logger

# ── Handler/middleware signatures ────────────────────────────────────────

# Handler: receives parsed request, returns result dict or raises
Handler = Callable[
    [str, dict[str, Any], str, str | None, "ClientSessionRegistry"],
    Coroutine[Any, Any, dict[str, Any]],
]

# Middleware: wraps the next call in chain
Middleware = Callable[
    [str, str, dict[str, Any], str, str | None,
     Callable[..., Coroutine[Any, Any, dict[str, Any]]]],
    Coroutine[Any, Any, dict[str, Any]],
]


# ── Error codes ──────────────────────────────────────────────────────────

class AppServerError(Exception):
    """Typed error from handler or middleware that AppServer catches."""
    def __init__(self, message: str, *, code: str = "INTERNAL", recoverable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.recoverable = recoverable


# ── ClientSessionRegistry ────────────────────────────────────────────────


class ClientSessionRegistry:
    """Manages client_id ↔ session_id relationships with TTL eviction.

    One client can access many sessions. One session can have many
    authorized clients. Sessions are created explicitly; authorization
    is explicit (not implied by key format).
    """

    def __init__(self, *, idle_timeout_seconds: int = 3600):
        self._client_sessions: dict[str, set[str]] = {}   # client_id → {session_id}
        self._session_clients: dict[str, set[str]] = {}   # session_id → {client_id}
        self._sessions: dict[str, Any] = {}               # session_id → RuntimeSession
        self._last_activity: dict[str, float] = {}         # session_id → timestamp
        self._idle_timeout = idle_timeout_seconds

    # ── client_id resolution ─────────────────────────────────────────────

    def resolve_client_id(self, raw: str | None) -> str:
        """Resolve a client_id, generating a legacy shim if missing.

        Phase 26 compatibility shim: when the Desktop frontend hasn't
        been updated to send client_id yet, generate one with a warning.
        This shim MUST be removed in Phase 27 — client_id will be required.
        """
        if raw:
            return raw
        generated = f"legacy-desktop-{uuid.uuid4().hex[:8]}"
        warnings.warn(
            f"client_id not provided — generated {generated}. "
            f"client_id will be REQUIRED in Phase 27.",
            UserWarning,
            stacklevel=2,
        )
        return generated

    # ── session lifecycle ────────────────────────────────────────────────

    async def create_session(
        self,
        *,
        client_id: str,
        session_key: str,
        config: Any,
        provider: Any,
        workspace: Path,
    ) -> Any:
        """Create a new RuntimeSession and authorize the creating client."""
        from miqi.runtime.session import RuntimeSession

        # Phase 26: session_id is namespaced client_id:session_key
        # In Phase 27, switch to a pure opaque session_id with display name.
        session_id = f"{client_id}:{session_key}"

        existing = self._sessions.get(session_id)
        if existing is not None:
            # Session already exists — ensure client is authorized
            self._client_sessions.setdefault(client_id, set()).add(session_id)
            self._session_clients.setdefault(session_id, set()).add(client_id)
            self._last_activity[session_id] = time.time()
            return existing

        runtime = RuntimeSession.create(
            config=config,
            provider=provider,
            session_id=session_id,
            workspace=workspace,
        )
        await runtime.start()

        self._sessions[session_id] = runtime
        self._client_sessions.setdefault(client_id, set()).add(session_id)
        self._session_clients[session_id] = {client_id}
        self._last_activity[session_id] = time.time()
        logger.info(
            "ClientSessionRegistry: created session {} for client {}",
            session_id, client_id,
        )
        return runtime

    async def get_session(self, client_id: str, session_id: str) -> Any | None:
        """Return RuntimeSession if client is authorized, else None."""
        authorized = self._session_clients.get(session_id, set())
        if client_id not in authorized:
            return None
        self._last_activity[session_id] = time.time()
        return self._sessions.get(session_id)

    def authorize_client(
        self, owner_client_id: str, session_id: str, target_client_id: str,
    ) -> bool:
        """Grant another client access to a session.

        Only an existing authorized client can grant access to others.
        """
        authorized = self._session_clients.get(session_id, set())
        if owner_client_id not in authorized:
            return False
        self._client_sessions.setdefault(target_client_id, set()).add(session_id)
        self._session_clients[session_id].add(target_client_id)
        return True

    def list_sessions(self, client_id: str) -> list[str]:
        """Return session_ids this client is authorized for."""
        return sorted(self._client_sessions.get(client_id, set()))

    def get_session_client_ids(self, session_id: str) -> set[str]:
        """Return all client_ids authorized for a session."""
        return self._session_clients.get(session_id, set()).copy()

    async def stop_session(self, session_id: str) -> None:
        """Stop a RuntimeSession and remove it from all client mappings."""
        runtime = self._sessions.pop(session_id, None)
        if runtime is None:
            return
        try:
            await runtime.stop()
        except Exception as exc:
            logger.warning(
                "ClientSessionRegistry: error stopping session {}: {}",
                session_id, exc,
            )
        # Remove from all client mappings
        for client_set in self._client_sessions.values():
            client_set.discard(session_id)
        self._session_clients.pop(session_id, None)
        self._last_activity.pop(session_id, None)

    async def stop_all(self) -> None:
        """Stop all sessions (shutdown hook)."""
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self.stop_session(sid)

    async def evict_idle_sessions(self) -> list[str]:
        """Evict sessions idle beyond TTL. Returns list of evicted session_ids."""
        now = time.time()
        evicted: list[str] = []
        for sid, last_active in list(self._last_activity.items()):
            if now - last_active > self._idle_timeout:
                logger.info(
                    "ClientSessionRegistry: evicting idle session {} (last active {}s ago)",
                    sid, int(now - last_active),
                )
                await self.stop_session(sid)
                evicted.append(sid)
        return evicted

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    @property
    def client_count(self) -> int:
        return len(self._client_sessions)


# ── AppServer ────────────────────────────────────────────────────────────


class AppServer:
    """Transport-agnostic protocol server with method dispatch and middleware.

    Usage:
        registry = ClientSessionRegistry()
        server = AppServer(registry)
        server.register_method("chat.send", chat_send_handler)
        server.add_middleware(auth_middleware)
        response = await server.dispatch(req_id, method, params, client_id, session_id)
    """

    def __init__(self, registry: ClientSessionRegistry, *, ttl_interval_seconds: int = 300):
        self.registry = registry
        self._methods: dict[str, Handler] = {}
        self._middleware: list[Middleware] = []
        self._ttl_interval = ttl_interval_seconds
        self._ttl_task: asyncio.Task | None = None
        self._running = False

    # ── method registration ──────────────────────────────────────────────

    def register_method(self, method: str, handler: Handler) -> None:
        """Register a handler for a method name.

        Handler signature:
            async def handler(request_id, params, client_id, session_id, registry) -> dict

        The returned dict should be either {"result": ...} on success or
        raise AppServerError on expected errors. Unexpected exceptions
        are caught and sanitized by the dispatch layer.
        """
        self._methods[method] = handler
        logger.debug("AppServer: registered method {}", method)

    # ── middleware ───────────────────────────────────────────────────────

    def add_middleware(self, middleware: Middleware) -> None:
        """Add middleware to the chain. Middleware runs in registration order.

        Middleware signature:
            async def mw(request_id, method, params, client_id, session_id, next_handler) -> dict

        Middleware can:
        - Modify params before passing to next_handler
        - Return early (block the request) without calling next_handler
        - Modify the response from next_handler
        """
        self._middleware.append(middleware)

    # ── dispatch ─────────────────────────────────────────────────────────

    async def dispatch(
        self,
        request_id: str,
        method: str,
        params: dict[str, Any],
        client_id: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a request through middleware chain to the handler.

        Returns a response envelope: {"request_id": ..., "result": ...}
        or an error envelope: {"request_id": ..., "error": ..., "code": ..., "recoverable": ...}

        This is the single entry point for all transport adapters.
        """
        try:
            return await self._dispatch_inner(request_id, method, params, client_id, session_id)
        except AppServerError as exc:
            logger.warning(
                "AppServer: error dispatching {} {} (client={}): {}",
                method, request_id, client_id, exc.message,
            )
            return {
                "request_id": request_id,
                "error": exc.message,
                "code": exc.code,
                "recoverable": exc.recoverable,
            }
        except Exception as exc:
            logger.exception(
                "AppServer: internal error dispatching {} {} (client={})",
                method, request_id, client_id,
            )
            return {
                "request_id": request_id,
                "error": "Internal error",
                "code": "INTERNAL",
                "recoverable": False,
            }

    async def _dispatch_inner(
        self,
        request_id: str,
        method: str,
        params: dict[str, Any],
        client_id: str,
        session_id: str | None,
    ) -> dict[str, Any]:
        # 1. Look up handler
        handler = self._methods.get(method)
        if handler is None:
            return {
                "request_id": request_id,
                "error": f"Unknown method: {method}",
                "code": "UNKNOWN_METHOD",
                "recoverable": False,
            }

        # 2. Check session authorization (if session-scoped)
        if session_id is not None:
            session = await self.registry.get_session(client_id, session_id)
            if session is None:
                return {
                    "request_id": request_id,
                    "error": f"Not authorized for session {session_id}",
                    "code": "UNAUTHORIZED",
                    "recoverable": False,
                }

        # 3. Build the middleware chain ending in the handler
        async def _handler_wrapper(
            req_id: str, meth: str, p: dict[str, Any], cid: str, sid: str | None,
        ) -> dict[str, Any]:
            return await handler(req_id, p, cid, sid, self.registry)

        # Wrap handler through middleware chain (outermost first)
        wrapped: Any = _handler_wrapper
        for mw in reversed(self._middleware):
            outer = mw
            inner = wrapped

            async def _mw_bound(
                req_id: str, meth: str, p: dict[str, Any], cid: str, sid: str | None,
                _outer=outer, _inner=inner,
            ) -> dict[str, Any]:
                return await _outer(req_id, meth, p, cid, sid, _inner)

            wrapped = _mw_bound

        result = await wrapped(request_id, method, params, client_id, session_id)

        # 4. Ensure response has request_id
        if "request_id" not in result:
            result = {"request_id": request_id, **result}
        return result

    # ── lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the AppServer and background TTL eviction task."""
        if self._running:
            return
        self._running = True
        self._ttl_task = asyncio.create_task(self._run_ttl_loop())
        logger.info("AppServer started (TTL interval={}s)", self._ttl_interval)

    async def stop(self) -> None:
        """Stop the AppServer, cancel TTL task, and stop all sessions."""
        self._running = False
        if self._ttl_task is not None and not self._ttl_task.done():
            self._ttl_task.cancel()
            try:
                await self._ttl_task
            except asyncio.CancelledError:
                pass
            self._ttl_task = None
        await self.registry.stop_all()
        logger.info("AppServer stopped")

    async def _run_ttl_loop(self) -> None:
        """Background task that periodically evicts idle sessions."""
        while self._running:
            try:
                await asyncio.sleep(self._ttl_interval)
                if not self._running:
                    break
                evicted = await self.registry.evict_idle_sessions()
                if evicted:
                    logger.info(
                        "AppServer TTL: evicted {} idle session(s): {}",
                        len(evicted), evicted,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("AppServer TTL loop error: {}", exc)

    # ── event fanout (stub for 26.4) ─────────────────────────────────────

    async def emit_event(self, client_id: str, event_type: str, data: Any, *, request_id: str | None = None) -> None:
        """Placeholder — event fanout implemented in Task 26.4."""
        pass
