"""Codex-style thread AppServer handlers.

Registers thread/start, thread/resume, thread/fork, thread/read,
thread/turns/list, thread/turns/items/list, thread/name/set,
thread/rollback, and thread/loaded/list on an AppServer instance.
"""

from __future__ import annotations

from typing import Any

from miqi.runtime.app_server import AppServer, AppServerError, get_bridge_state
from miqi.runtime.thread_protocol import page_items
from miqi.runtime.thread_projection import ThreadProjectionRuntime


def register_codex_thread_handlers(server: AppServer) -> None:
    """Register all Codex-style thread methods on an AppServer instance."""

    async def _thread_start(request_id, params, client_id, session_id, registry):
        session = await _get_or_create_session(registry, client_id, params)
        threads = session.services.thread_runtime
        projection = _projection(session)
        thread = await threads.create_thread(
            title=params.get("title") or params.get("name") or "New thread",
            thread_id=params.get("threadId") or params.get("thread_id"),
            ephemeral=bool(params.get("ephemeral", False)),
            cwd=params.get("cwd"),
            metadata={"source": params.get("sessionStartSource", "startup")},
        )
        server.subscribe(client_id, session.session_id)
        view = await projection.read_thread(thread.thread_id, include_turns=True)
        await server.emit_event(
            session.session_id, "thread/started", {"thread": view.to_dict()},
        )
        return {"result": {"thread": view.to_dict()}}

    async def _thread_resume(request_id, params, client_id, session_id, registry):
        session = await _get_or_create_session(registry, client_id, params)
        projection = _projection(session)
        thread_id = params["threadId"]
        include_turns = not bool(params.get("excludeTurns", False))
        view = await projection.read_thread(
            thread_id,
            include_turns=include_turns,
            items_view=params.get("itemsView", "summary"),
        )
        server.subscribe(client_id, session.session_id)
        await server.emit_event(
            session.session_id, "thread/started", {"thread": view.to_dict()},
        )
        return {"result": {"thread": view.to_dict()}}

    async def _thread_fork(request_id, params, client_id, session_id, registry):
        session = await _get_or_create_session(registry, client_id, params)
        threads = session.services.thread_runtime
        ledger = session.services.ledger_runtime
        history = getattr(session.services, "history_runtime", None)
        projection = _projection(session)
        source_id = params["threadId"]
        child = await threads.fork_thread(
            source_id,
            title=params.get("title", "Fork"),
        )
        if ledger is not None:
            await ledger.copy_thread_items(source_id, child.thread_id)
        if history is not None and hasattr(history, "copy_thread_items"):
            await history.copy_thread_items(source_id, child.thread_id)
        view = await projection.read_thread(
            child.thread_id,
            include_turns=not bool(params.get("excludeTurns", False)),
            items_view=params.get("itemsView", "summary"),
        )
        await server.emit_event(
            session.session_id, "thread/started", {"thread": view.to_dict()},
        )
        return {"result": {"thread": view.to_dict()}}

    async def _thread_read(request_id, params, client_id, session_id, registry):
        session = await _require_session(registry, client_id, session_id)
        view = await _projection(session).read_thread(
            params["threadId"],
            include_turns=bool(params.get("includeTurns", False)),
            items_view=params.get("itemsView", "summary"),
        )
        return {"result": {"thread": view.to_dict()}}

    async def _thread_turns_list(request_id, params, client_id, session_id, registry):
        session = await _require_session(registry, client_id, session_id)
        projection = _projection(session)
        turns = await projection.list_turns(
            params["threadId"],
            items_view=params.get("itemsView", "summary"),
        )
        page = page_items(
            [turn.to_dict() for turn in turns],
            limit=int(params.get("limit", 50)),
            cursor=params.get("cursor"),
            sort_direction=params.get("sortDirection", "desc"),
        )
        return {"result": page.to_dict()}

    async def _thread_turns_items_list(request_id, params, client_id, session_id, registry):
        raise AppServerError(
            "thread/turns/items/list is not supported yet",
            code="UNSUPPORTED_METHOD",
            recoverable=False,
        )

    async def _thread_name_set(request_id, params, client_id, session_id, registry):
        session = await _require_session(registry, client_id, session_id)
        thread = await session.services.thread_runtime.rename_thread(
            params["threadId"], params["name"],
        )
        view = await _projection(session).read_thread(thread.thread_id, include_turns=False)
        await server.emit_event(
            session.session_id, "thread/name/updated",
            {"threadId": thread.thread_id, "name": thread.title},
        )
        return {"result": {"thread": view.to_dict()}}

    async def _thread_rollback(request_id, params, client_id, session_id, registry):
        session = await _require_session(registry, client_id, session_id)
        thread_id = params["threadId"]
        drop_last_turns = int(params.get("dropLastTurns", params.get("numTurns", 1)))
        if drop_last_turns < 1:
            raise AppServerError("dropLastTurns must be >= 1", code="INVALID_PARAMS")
        marker = await session.services.ledger_runtime.append_rollback_marker(
            thread_id,
            drop_last_turns=drop_last_turns,
        )
        removed = list(marker.payload.get("removed_turn_ids", []))
        history = getattr(session.services, "history_runtime", None)
        if history is not None:
            await history.delete_turn_items(thread_id, removed)
        view = await _projection(session).read_thread(
            thread_id,
            include_turns=True,
            items_view=params.get("itemsView", "summary"),
        )
        await server.emit_event(
            session.session_id, "thread/rollback",
            {
                "threadId": thread_id,
                "removedTurnIds": removed,
            },
        )
        return {"result": {"thread": view.to_dict()}}

    async def _thread_loaded_list(request_id, params, client_id, session_id, registry):
        loaded = []
        for sid, clients in registry._session_clients.items():
            if client_id in clients:
                session = await registry.get_session(client_id, sid)
                if session is None:
                    continue
                threads = await session.services.thread_runtime.list_threads(include_archived=False)
                loaded.extend(t.thread_id for t in threads)
        return {"result": {"threadIds": sorted(set(loaded))}}

    server.register_method("thread/start", _thread_start)
    server.register_method("thread/resume", _thread_resume)
    server.register_method("thread/fork", _thread_fork)
    server.register_method("thread/read", _thread_read)
    server.register_method("thread/turns/list", _thread_turns_list)
    server.register_method("thread/turns/items/list", _thread_turns_items_list)
    server.register_method("thread/name/set", _thread_name_set)
    server.register_method("thread/rollback", _thread_rollback)
    server.register_method("thread/loaded/list", _thread_loaded_list)


def _projection(session: Any) -> ThreadProjectionRuntime:
    return ThreadProjectionRuntime(
        session.services.thread_runtime,
        session.services.ledger_runtime,
        session.services.replay_runtime,
    )


async def _get_or_create_session(registry: Any, client_id: str, params: dict) -> Any:
    """Get or create a RuntimeSession for session-creating handlers."""
    session_key = params.get("sessionKey") or params.get("session_key") or "default"
    session_id = params.get("sessionId") or params.get("session_id") or f"{client_id}:{session_key}"

    # Check if session already exists
    session = await registry.get_session(client_id, session_id)
    if session is not None:
        return session

    # Create new session using bridge context
    state = get_bridge_state(registry)
    config = state.load_config()
    from miqi.providers.factory import make_provider
    provider = make_provider(config)
    workspace = config.workspace_path

    return await registry.create_session(
        client_id=client_id,
        session_key=session_id,
        config=config,
        provider=provider,
        workspace=workspace,
    )


async def _require_session(registry: Any, client_id: str, session_id: str | None) -> Any:
    """Require that a session exists and client is authorized."""
    if session_id is None:
        raise AppServerError("session_id is required", code="INVALID_PARAMS")
    session = await registry.get_session(client_id, session_id)
    if session is None:
        raise AppServerError("Not authorized", code="UNAUTHORIZED")
    return session
