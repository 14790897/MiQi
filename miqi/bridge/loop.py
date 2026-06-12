"""Bridge runtime loop — persistent asyncio event loop for the bridge process.

Phase 27.1: Replaces the per-request asyncio.run() pattern with a single
persistent event loop. stdin is read by a background thread and pushed
into an asyncio.Queue; the persistent loop drains the queue and dispatches
each request through AppServer (for migrated methods) or legacy _dispatch().
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import traceback
import uuid
import warnings
from pathlib import Path
from typing import Any

from loguru import logger


class BridgeRuntimeLoop:
    """Persistent asyncio event loop for the bridge transport.

    Owns the AppServer, stdin reader, and dispatch loop. Created once
    in main() and runs for the lifetime of the bridge process.

    Usage:
        bridge = BridgeRuntimeLoop(
            send_func=_send,
            dispatch_legacy_func=_dispatch,
            dev_mode=False,
        )
        bridge.start()  # blocks until stdin closes
    """

    def __init__(
        self,
        *,
        send_func: Any = None,
        dispatch_legacy_func: Any = None,
        bridge_state: Any = None,
        dev_mode: bool = False,
    ):
        self._send = send_func
        self._dispatch_legacy = dispatch_legacy_func
        self._bridge_state = bridge_state  # BridgeState for config/provider
        self._dev_mode = dev_mode
        self._loop: asyncio.AbstractEventLoop | None = None
        self._app_server: Any = None
        self._stdin_queue: asyncio.Queue | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._pending_tasks: set[asyncio.Task] = set()
        self._terminal_sent: set[str] = set()  # prevent duplicate terminal events
        self._active_chat_tasks: dict[str, asyncio.Task] = {}  # req_id → drain task

    # ── public API ─────────────────────────────────────────────────────────

    @property
    def app_server(self) -> Any:
        """Return the AppServer instance (for tests)."""
        return self._app_server

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """Return the persistent event loop (for tests)."""
        return self._loop

    def start(self) -> None:
        """Create persistent loop, run the bridge, clean up.

        Blocks until stdin closes (EOF). Catches KeyboardInterrupt
        for graceful Ctrl+C shutdown.
        """
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        except KeyboardInterrupt:
            logger.info("BridgeRuntimeLoop interrupted")
        finally:
            # Cancel any remaining tasks
            try:
                self._cancel_all_tasks()
            except Exception:
                pass
            # Shutdown async generators
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            except Exception:
                pass
            self._loop.close()
            logger.info("BridgeRuntimeLoop stopped")

    # ── main coroutine ─────────────────────────────────────────────────────

    async def _run(self) -> None:
        """Main coroutine running on the persistent loop.

        Sequence:
        1. Create and start AppServer
        2. Register event sink for Desktop transport
        3. Start stdin reader thread
        4. Drain request queue (blocking)
        5. Shutdown
        """
        # 1. Create AppServer
        await self._init_app_server()

        # 2. Register event sink so AppServer events reach Desktop stdout
        self._setup_event_sink()

        # 3. Expose _app_server global so legacy code can find it
        self._publish_app_server()

        # 4. Start stdin reader thread
        self._stdin_queue = asyncio.Queue(maxsize=256)
        self._shutdown_event = asyncio.Event()

        reader_thread = threading.Thread(
            target=self._stdin_reader,
            daemon=True,
            name="bridge-stdin-reader",
        )
        reader_thread.start()
        logger.info("BridgeRuntimeLoop: stdin reader started")

        # 5. Drain request queue
        await self._drain_loop()

        # 6. Shutdown
        await self._shutdown()

    # ── AppServer initialization ───────────────────────────────────────────

    async def _init_app_server(self) -> None:
        """Create AppServer with ClientSessionRegistry and register handlers."""
        from miqi.runtime.app_server import (
            AppServer,
            ClientSessionRegistry,
            register_command_handlers,
            register_replay_handlers,
        )

        registry = ClientSessionRegistry()
        self._app_server = AppServer(registry)
        await self._app_server.start()

        # Register bridge-owned handlers
        self._app_server.register_method("status", self._status_handler)

        # Register Phase 27.3: chat.send through AppServer
        self._app_server.register_method("chat.send", self._chat_send_handler)

        # Register Phase 26.5 replay handlers
        register_replay_handlers(self._app_server)

        # Register Phase 26.6 command handlers (thread.*, chat.abort)
        register_command_handlers(self._app_server)

        logger.info(
            "BridgeRuntimeLoop: AppServer initialized with {} methods",
            len(self._app_server._methods),
        )

    async def _status_handler(
        self, _request_id: str, _params: dict, _client_id: str,
        _session_id: str | None, _registry: Any,
    ) -> dict:
        """Bridge status check — session-less handler."""
        config_exists = Path.home() / ".miqi" / "config.json"
        return {
            "result": {
                "status": "ok",
                "configured": config_exists.exists(),
                "python_version": sys.version,
            },
        }

    # ── chat.send handler ──────────────────────────────────────────────────

    async def _chat_send_handler(
        self, request_id: str, params: dict, client_id: str,
        session_id: str | None, registry: Any,
    ) -> dict:
        """AppServer handler for chat.send.

        Submits the user message to RuntimeSession, spawns a background
        task to drain events, and returns immediately with {"accepted": true}.
        Streaming events are forwarded through AppServer.emit_event().
        """
        from miqi.protocol.commands import UserMessage

        content = params.get("content")
        if not content:
            from miqi.runtime.app_server import AppServerError

            raise AppServerError("content is required", code="INVALID_PARAMS")

        session_key = params.get("session_key", "desktop:default")
        thread_id = params.get("thread_id", session_key)

        # Get or create RuntimeSession
        runtime_id = session_id or f"{client_id}:{session_key}"
        runtime = await registry.get_session(client_id, runtime_id)
        if runtime is None:
            if self._bridge_state is None:
                from miqi.runtime.app_server import AppServerError

                raise AppServerError(
                    "Bridge state not available for session creation",
                    code="INTERNAL",
                )
            config = self._bridge_state.load_config()
            from miqi.providers.factory import make_provider

            provider = make_provider(config)
            runtime = await registry.create_session(
                client_id=client_id,
                session_key=runtime_id,
                config=config,
                provider=provider,
                workspace=config.workspace_path,
            )

        # Submit the user message
        await runtime.submit(UserMessage(content=content, thread_id=thread_id))

        # Spawn background drain task
        app_server = self._app_server
        task = asyncio.create_task(
            self._drain_chat_events(
                request_id=request_id,
                runtime=runtime,
                thread_id=thread_id,
                session_id=runtime_id,
                client_id=client_id,
            )
        )
        self._active_chat_tasks[request_id] = task
        # Clean up task reference when done
        task.add_done_callback(lambda t: self._active_chat_tasks.pop(request_id, None))

        logger.info(
            "chat.send: submitted turn for client={} session={} thread={}",
            client_id, runtime_id, thread_id,
        )
        return {"result": {"accepted": True}}

    async def _drain_chat_events(
        self,
        request_id: str,
        runtime: Any,
        thread_id: str,
        session_id: str,
        client_id: str,
    ) -> None:
        """Background task: drain events from RuntimeSession and forward them.

        Runs on the persistent loop. Forwards progress/approval events via
        AppServer.emit_event(). Sends terminal event (final/error/aborted)
        when the turn completes.
        """
        app_server = self._app_server

        async def _emit(event_type: str, data: Any) -> None:
            """Emit a non-terminal event through AppServer fanout."""
            await app_server.emit_event(
                session_id, event_type, data,
                request_id=request_id,
            )

        async def _emit_terminal(event_type: str, data: Any) -> bool:
            """Emit a terminal event, preventing duplicates."""
            if request_id in self._terminal_sent:
                return False
            self._terminal_sent.add(request_id)
            await app_server.emit_event(
                session_id, event_type, data,
                request_id=request_id,
            )
            return True

        try:
            from dataclasses import asdict, is_dataclass

            from miqi.protocol.events import (
                AgentMessageEvent,
                ErrorEvent,
                TurnCompleteEvent,
            )

            while True:
                event = await runtime.next_event(timeout=300)
                if event is None:
                    # Timeout — no response from agent
                    await _emit_terminal("error", {
                        "message": "Turn timed out after 300s",
                    })
                    break

                if isinstance(event, AgentMessageEvent):
                    await _emit_terminal("final", {
                        "content": event.content,
                        "aborted": False,
                    })
                    break

                if isinstance(event, ErrorEvent):
                    await _emit_terminal("error", {
                        "message": event.message,
                    })
                    break

                if isinstance(event, TurnCompleteEvent):
                    await _emit_terminal("final", {
                        "content": "",
                        "aborted": False,
                        "status": "completed",
                    })
                    break

                # Forward all other events as progress
                event_name = event.__class__.__name__
                if is_dataclass(event):
                    payload = asdict(event)
                else:
                    payload = getattr(event, "__dict__", {})

                if event_name == "ApprovalRequestedEvent":
                    await _emit("approval_request", payload)
                else:
                    await _emit("progress", {
                        "event": event_name,
                        "data": payload,
                    })

        except asyncio.CancelledError:
            await _emit_terminal("aborted", {
                "message": "Chat aborted by user",
            })
        except Exception as exc:
            logger.warning(
                "chat.send drain error for request {}: {}", request_id, exc,
            )
            await _emit_terminal("error", {
                "message": str(exc),
            })

    # ── event sink ─────────────────────────────────────────────────────────

    def _setup_event_sink(self) -> None:
        """Register the Desktop transport event sink on AppServer.

        Translates AppServer event envelopes to the legacy bridge
        wire format that Desktop expects:
          AppServer: {"request_id": ..., "event": ..., "data": ...}
          Bridge:    {"id": ..., "type": ..., "data": ...}
        """
        send = self._send

        async def _desktop_sink(envelope: dict) -> None:
            send({
                "id": envelope.get("request_id"),
                "type": envelope["event"],
                "data": envelope["data"],
            })

        self._app_server.set_event_sink("desktop", _desktop_sink)
        logger.debug("BridgeRuntimeLoop: desktop event sink registered")

    def _publish_app_server(self) -> None:
        """Set the _app_server module global in server.py for backward compat."""
        try:
            import miqi.bridge.server as bridge_module

            bridge_module._app_server = self._app_server
        except Exception:
            pass

    # ── stdin reader ───────────────────────────────────────────────────────

    def _stdin_reader(self) -> None:
        """Read lines from stdin and push them into the async queue.

        Runs in a daemon thread. Uses run_coroutine_threadsafe() to
        safely push items into the queue owned by the persistent loop.
        A None sentinel is pushed when stdin closes (EOF).
        """
        loop = self._loop
        queue = self._stdin_queue
        if loop is None or queue is None:
            return
        try:
            for line in sys.stdin:
                raw = line.strip()
                try:
                    asyncio.run_coroutine_threadsafe(queue.put(raw), loop)
                except Exception:
                    # Loop likely closed — stop reading
                    break
        except Exception:
            pass
        finally:
            # Signal EOF
            try:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            except Exception:
                pass

    # ── dispatch ───────────────────────────────────────────────────────────

    async def _drain_loop(self) -> None:
        """Drain the stdin queue and dispatch each request.

        For methods registered on AppServer, dispatch through
        AppServer.dispatch() on the persistent loop.
        For legacy methods, call the sync dispatch function directly
        (legacy handlers are fast enough to run synchronously; slow
        ones like chat.send are migrated in subsequent commits).
        """
        dispatch_legacy = self._dispatch_legacy
        app_server = self._app_server
        send = self._send
        queue = self._stdin_queue
        if queue is None:
            logger.error("BridgeRuntimeLoop: stdin queue not initialized")
            return

        while True:
            line = await queue.get()
            if line is None:  # EOF sentinel
                logger.info("BridgeRuntimeLoop: stdin closed, stopping dispatch")
                break
            if not line:
                continue

            req_id = "?"
            try:
                req = json.loads(line)
                method = req["method"]
                req_id = req["id"]
                params = req.get("params", {})

                # Check if this method is registered on AppServer
                if method in getattr(app_server, "_methods", {}):
                    client_id = self._resolve_client_id(params)
                    session_id = params.get("session_key") or params.get("session_id")

                    response = await app_server.dispatch(
                        request_id=req_id,
                        method=method,
                        params=params,
                        client_id=client_id,
                        session_id=session_id,
                    )
                    send(response)
                elif dispatch_legacy is not None:
                    # Legacy handler path (sync functions)
                    dispatch_legacy(req_id, method, params)
                else:
                    send({
                        "id": req_id,
                        "error": f"Unknown method: {method}",
                        "code": "UNKNOWN_METHOD",
                        "recoverable": False,
                    })
            except json.JSONDecodeError as exc:
                logger.warning("BridgeRuntimeLoop: invalid JSON: {}", exc)
                try:
                    send({"id": req_id, "error": "Invalid JSON"})
                except Exception:
                    pass
            except Exception:
                logger.error(
                    "BridgeRuntimeLoop: unhandled error: {}",
                    traceback.format_exc(),
                )
                try:
                    send({"id": req_id, "error": "Internal bridge error"})
                except Exception:
                    pass

    def _resolve_client_id(self, params: dict) -> str:
        """Resolve client_id from request params.

        Phase 27.1-27.4: compatibility shim generates a legacy ID with
        warning. Phase 27.5 will make this required and reject missing IDs.
        In dev_mode, a predictable dev- prefix is used.
        """
        raw = params.get("client_id") or params.get("caller_id") or params.get("user_id")
        if raw:
            return raw
        if self._dev_mode:
            return f"dev-{uuid.uuid4().hex[:6]}"
        # Compatibility shim — will be removed in 27.5
        generated = f"legacy-desktop-{uuid.uuid4().hex[:8]}"
        warnings.warn(
            f"client_id not provided — generated {generated}. "
            f"client_id will be REQUIRED in a future phase.",
            UserWarning,
            stacklevel=2,
        )
        return generated

    # ── shutdown ───────────────────────────────────────────────────────────

    async def _shutdown(self) -> None:
        """Graceful shutdown sequence.

        1. Stop AppServer (stops all RuntimeSessions, cancels TTL task)
        2. Cancel all pending asyncio tasks
        """
        logger.info("BridgeRuntimeLoop: starting graceful shutdown")

        # 1. Stop AppServer
        if self._app_server is not None:
            try:
                await self._app_server.stop()
            except Exception as exc:
                logger.warning(
                    "BridgeRuntimeLoop: error stopping AppServer: {}", exc,
                )

        # 2. Signal shutdown complete
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        logger.info("BridgeRuntimeLoop: shutdown complete")

    def _cancel_all_tasks(self) -> None:
        """Cancel all pending asyncio tasks on the loop.

        Called during loop cleanup in start()'s finally block.
        Must be called while the loop is still running.
        """
        if self._loop is None:
            return
        pending = [
            t for t in asyncio.all_tasks(self._loop)
            if not t.done()
        ]
        if not pending:
            return
        logger.info(
            "BridgeRuntimeLoop: cancelling {} pending task(s)", len(pending),
        )
        for task in pending:
            task.cancel()
        # Give tasks a moment to cancel
        try:
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True),
            )
        except Exception:
            pass
