"""Codex-style thread AppServer handlers.

Registers thread/start, thread/resume, thread/fork, thread/read,
thread/turns/list, thread/turns/items/list, thread/name/set,
thread/rollback, thread/loaded/list, thread/list, thread/export,
and thread/import on an AppServer instance.

Phase 39: thread/read and thread/turns/list now support stored
fallback when no live RuntimeSession is available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.runtime.app_server import AppServer, AppServerError, get_bridge_state
from miqi.runtime.stored_runtime import (
    StoredRuntimeReader,
    StoredThreadAmbiguous,
    StoredThreadError,
    StoredThreadNotFound,
    StoredThreadUnauthorized,
)
from miqi.runtime.thread_projection import (
    ThreadProjectionRuntime,
    project_stored_thread,
    project_stored_turns,
)
from miqi.runtime.thread_protocol import page_items


def register_codex_thread_handlers(server: AppServer) -> None:
    """Register all Codex-style thread methods on an AppServer instance."""

    async def _thread_start(request_id, params, client_id, session_id, registry):
        # Respect dispatch session_id when provided; otherwise derive from params.
        if session_id is not None:
            session = await _require_session(registry, client_id, session_id)
        else:
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
        # Respect dispatch session_id when provided; otherwise derive from params.
        if session_id is not None:
            session = await _require_session(registry, client_id, session_id)
        else:
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
        # Respect dispatch session_id when provided; otherwise derive from params.
        if session_id is not None:
            session = await _require_session(registry, client_id, session_id)
        else:
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
        thread_id = params.get("threadId")
        if not thread_id:
            raise AppServerError("threadId is required", code="INVALID_PARAMS")
        include_turns = bool(params.get("includeTurns", False))
        items_view = params.get("itemsView", "summary")

        # Live-first: if the caller already has a live session, use it.
        if session_id is not None:
            live = await registry.get_session(client_id, session_id)
            if live is not None:
                view = await _projection(live).read_thread(
                    thread_id, include_turns=include_turns, items_view=items_view
                )
                return {"result": {"thread": view.to_dict()}}

        # Stored fallback: read from the runtime DB without a live session.
        reader = _stored_reader(registry, client_id)
        try:
            bundle = await reader.load_bundle(
                thread_id,
                session_id=params.get("sessionId") or params.get("session_id") or session_id,
            )
        except Exception as exc:
            raise _stored_error(exc) from exc
        view = project_stored_thread(bundle, include_turns=include_turns, items_view=items_view)
        return {"result": {"thread": view.to_dict()}}

    async def _thread_turns_list(request_id, params, client_id, session_id, registry):
        thread_id = params.get("threadId")
        if not thread_id:
            raise AppServerError("threadId is required", code="INVALID_PARAMS")
        items_view = params.get("itemsView", "summary")
        limit = int(params.get("limit", 50))
        cursor = params.get("cursor")
        sort_direction = params.get("sortDirection", "desc")

        # Live-first path
        if session_id is not None:
            live = await registry.get_session(client_id, session_id)
            if live is not None:
                projection = _projection(live)
                turns = await projection.list_turns(thread_id, items_view=items_view)
                page = page_items(
                    [turn.to_dict() for turn in turns],
                    limit=limit, cursor=cursor, sort_direction=sort_direction,
                )
                return {"result": page.to_dict()}

        # Stored fallback
        reader = _stored_reader(registry, client_id)
        try:
            bundle = await reader.load_bundle(
                thread_id,
                session_id=params.get("sessionId") or params.get("session_id") or session_id,
            )
        except Exception as exc:
            raise _stored_error(exc) from exc
        turns = project_stored_turns(thread_id, bundle.ledger_items, items_view=items_view)
        page = page_items(
            [turn.to_dict() for turn in turns],
            limit=limit, cursor=cursor, sort_direction=sort_direction,
        )
        return {"result": page.to_dict()}

    async def _thread_turns_items_list(request_id, params, client_id, session_id, registry):
        raise AppServerError(
            "thread/turns/items/list is not supported yet",
            code="UNSUPPORTED_METHOD",
            recoverable=False,
        )

    async def _thread_list(request_id, params, client_id, session_id, registry):
        reader = _stored_reader(registry, client_id)
        threads = await reader.list_threads(
            include_archived=bool(params.get("archived", False)),
            session_id=params.get("sessionId") or params.get("session_id"),
            cwd=params.get("cwd"),
            search_term=params.get("searchTerm"),
        )
        views = []
        for thread in threads:
            bundle = await reader.load_bundle(thread.thread_id, session_id=thread.session_id)
            views.append(project_stored_thread(bundle, include_turns=False).to_dict())
        page = page_items(
            views,
            limit=int(params.get("limit", 50)),
            cursor=params.get("cursor"),
            sort_direction=params.get("sortDirection", "desc"),
        )
        return {"result": page.to_dict()}

    async def _thread_export(request_id, params, client_id, session_id, registry):
        thread_id = params.get("threadId")
        if not thread_id:
            raise AppServerError("threadId is required", code="INVALID_PARAMS")
        reader = _stored_reader(registry, client_id)
        try:
            bundle = await reader.load_bundle(
                thread_id,
                session_id=params.get("sessionId") or params.get("session_id") or session_id,
            )
        except Exception as exc:
            raise _stored_error(exc) from exc
        from miqi.runtime.thread_export import build_export_document
        document = build_export_document(
            thread=bundle.thread,
            ledger_items=bundle.ledger_items,
            provider_messages=[],
        )
        return {"result": {"document": document.to_dict()}}

    async def _thread_import(request_id, params, client_id, session_id, registry):
        document = params.get("document")
        if not isinstance(document, dict):
            raise AppServerError("document is required", code="INVALID_PARAMS")
        target_session_id = params.get("sessionId") or params.get("session_id") or session_id
        if target_session_id is None:
            session_key = params.get("sessionKey") or params.get("session_key") or "default"
            if str(session_key).startswith(f"{client_id}:"):
                session_key = str(session_key)[len(f"{client_id}:"):]
            target_session_id = f"{client_id}:{session_key}"
        reader = _stored_reader(registry, client_id)
        try:
            imported_thread_id = await reader.import_document(
                document,
                session_id=target_session_id,
                thread_id=params.get("threadId") or params.get("thread_id"),
                overwrite=bool(params.get("overwrite", False)),
            )
            bundle = await reader.load_bundle(imported_thread_id, session_id=target_session_id)
        except (StoredThreadError, StoredThreadUnauthorized) as exc:
            raise _stored_error(exc) from exc
        except Exception as exc:
            from loguru import logger
            logger.warning("thread/import failed: {}", exc)
            raise AppServerError("Thread import rejected", code="INVALID_PARAMS") from exc
        view = project_stored_thread(bundle, include_turns=bool(params.get("includeTurns", False)))
        return {"result": {"thread": view.to_dict()}}

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
    server.register_method("thread/list", _thread_list)
    server.register_method("thread/export", _thread_export)
    server.register_method("thread/import", _thread_import)
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
    """Get or create a RuntimeSession for session-creating handlers.

    Uses the raw session_key (e.g. "default", "project-a") so that
    ClientSessionRegistry.create_session produces the correctly namespaced
    session_id ``f"{client_id}:{session_key}"`` (e.g. "client-1:default").
    If params carries an explicit namespaced sessionId/session_id we check
    for that session first; when it doesn't exist we still create from the
    raw session_key so the registry owns the canonical id.
    """
    session_key = params.get("sessionKey") or params.get("session_key") or "default"
    # Defend against already-namespaced session_key (e.g. "client-1:default").
    # ClientSessionRegistry.create_session builds session_id as
    #   f"{client_id}:{session_key}"
    # so passing an already-namespaced value would produce a double-namespaced
    # id like "client-1:client-1:default". Strip the prefix when present.
    ns_prefix = f"{client_id}:"
    if session_key.startswith(ns_prefix):
        session_key = session_key[len(ns_prefix):]
    # Build the canonical session_id that create_session would produce.
    canonical_id = f"{client_id}:{session_key}"
    # Also accept an explicit sessionId (already-namespaced or bare).
    explicit_id = params.get("sessionId") or params.get("session_id")

    # Prefer the explicit id for existence check, fall back to canonical.
    lookup_id = explicit_id or canonical_id
    session = await registry.get_session(client_id, lookup_id)
    if session is not None:
        return session

    # Create new session using bridge context.
    state = get_bridge_state(registry)
    config = state.load_config()
    from miqi.providers.factory import make_provider
    provider = make_provider(config)
    workspace = config.workspace_path

    return await registry.create_session(
        client_id=client_id,
        session_key=session_key,
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


# ── Stored-thread helpers (Phase 39) ────────────────────────────────────────


def _runtime_db_path_from_registry(registry: Any) -> Path:
    state = get_bridge_state(registry)
    config = state.load_config()
    return config.workspace_path / ".miqi-runtime" / "runtime.db"


def _stored_reader(registry: Any, client_id: str) -> StoredRuntimeReader:
    return StoredRuntimeReader(_runtime_db_path_from_registry(registry), client_id=client_id)


def _stored_error(exc: Exception) -> AppServerError:
    if isinstance(exc, StoredThreadUnauthorized):
        return AppServerError("Not authorized", code="UNAUTHORIZED")
    if isinstance(exc, StoredThreadAmbiguous):
        return AppServerError("Multiple stored threads match; provide sessionId", code="AMBIGUOUS_THREAD")
    if isinstance(exc, StoredThreadNotFound):
        return AppServerError("Thread not found", code="NOT_FOUND")
    if isinstance(exc, StoredThreadError):
        return AppServerError("Stored thread read failed", code="INTERNAL")
    return AppServerError("Stored thread read failed", code="INTERNAL")
