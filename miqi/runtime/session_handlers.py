"""Session handlers for AppServer dispatch.

Phase 28.4: Migrates sessions.list, sessions.get, sessions.delete,
sessions.archive, sessions.unarchive, sessions.list_archived,
sessions.get_tracked_files, and sessions.clear_tracked_files from
bridge legacy handlers to AppServer async handlers.

Key semantics:
- sessions.list: merges active (AppServer registry) and inactive (disk)
  sessions for the requesting client. Active sessions show "running" status.
- sessions.get: checks AppServer registry first, falls back to SessionManager.
- sessions.delete: stops RuntimeSession if active, cleans AppServer registry,
  destroys sandbox, removes disk files.
- sessions.archive: stops RuntimeSession if active, cleans sandbox,
  marks archived on disk.
- Pure metadata handlers (unarchive, list_archived, tracked_files) remain
  thin wrappers but are gated through AppServer boundary.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError
from miqi.runtime.session_request_models import validate_session_params
from miqi.session.manager import OwnershipError


def _get_session_manager() -> Any:
    """Get a SessionManager for the current workspace."""
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()
    from miqi.session.manager import SessionManager
    return SessionManager(config.workspace_path)


def _client_session_id(client_id: str, session_key: str) -> str:
    """Compute the namespaced session_id used by AppServer registry."""
    return f"{client_id}:{session_key}"


# ── sessions.list ──────────────────────────────────────────────────────────


async def sessions_list_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """List sessions, merging AppServer registry (active) + disk (inactive).

    Active sessions (those running in the AppServer registry) are annotated
    with status: "running". Disk-only sessions get status: "inactive".
    Sessions from other clients are never visible.
    """
    validate_session_params("sessions.list", params)

    # Active sessions from AppServer registry
    active_sids: set[str] = set(registry.list_sessions(client_id))

    # Disk sessions from SessionManager (client-scoped)
    sm = _get_session_manager()
    disk_sessions: list[dict[str, Any]] = sm.list_sessions(client_id=client_id)

    # Merge: mark each as active, inactive, or unowned
    result_sessions: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for s in disk_sessions:
        key = s.get("key", "")
        if key in seen_keys:
            continue
        seen_keys.add(key)

        sid = _client_session_id(client_id, key)
        is_active = sid in active_sids
        ownership = s.get("ownership")

        status: str
        if is_active:
            status = "running"
        elif ownership == "unowned":
            status = "unowned"  # Legacy session — requires explicit claim
        else:
            status = "inactive"

        result_sessions.append({
            **s,
            "status": status,
        })

    # Add any active sessions not on disk
    for sid in active_sids:
        # extract key from client_id:session_key
        if sid.startswith(f"{client_id}:"):
            key = sid[len(client_id) + 1:]
        else:
            key = sid
        if key not in seen_keys:
            runtime = await registry.get_session(client_id, sid)
            result_sessions.append({
                "key": key,
                "title": key,
                "status": "running",
                "ownership": "owned",
                "created_at": None,
                "updated_at": None,
                "agent_count": len(getattr(getattr(runtime.services, "agent_control", None), "_agents", {})) if runtime else 0,
            })

    return {"result": {"sessions": result_sessions}}


# ── sessions.get ───────────────────────────────────────────────────────────


async def sessions_get_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Get session detail from AppServer registry or disk.

    If the session is active in AppServer, returns runtime info.
    Otherwise, falls back to SessionManager disk data.
    """
    typed = validate_session_params("sessions.get", params)
    session_key = typed.session_key

    sid = _client_session_id(client_id, session_key)

    # Check AppServer registry first
    runtime = await registry.get_session(client_id, sid)
    if runtime is not None:
        return {
            "result": {
                "key": session_key,
                "session_id": sid,
                "status": "running",
                "agent_count": len(getattr(getattr(runtime.services, "agent_control", None), "_agents", {})),
            },
        }

    # Fall back to SessionManager (client-scoped)
    sm = _get_session_manager()
    try:
        session = sm.get_or_create(session_key, client_id=client_id)
        sm.save(session)  # 立即持久化到磁盘，确保新会话可被 sidebar 列出 (fix #34)
        return {
            "result": {
                "key": session.key,
                "messages": session.messages,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata,
                "status": "inactive",
                "ownership": "owned",
            },
        }
    except OwnershipError as exc:
        raise AppServerError(exc.args[0], code=exc.code) from exc
    except Exception as exc:
        raise AppServerError(
            f"Failed to get session: {exc}",
            code="INTERNAL",
        ) from exc


# ── sessions.delete ────────────────────────────────────────────────────────


async def sessions_delete_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Delete a session: stop RuntimeSession, clean sandbox, remove disk files.

    Order:
    1. Stop RuntimeSession in AppServer registry (if active)
    2. Destroy sandbox
    3. Remove disk files via SessionManager
    """
    typed = validate_session_params("sessions.delete", params)
    session_key = typed.session_key

    import miqi.bridge.server as bridge_module

    sid = _client_session_id(client_id, session_key)

    # 1. Stop RuntimeSession if active
    runtime = await registry.get_session(client_id, sid)
    runtime_was_active = runtime is not None
    if runtime is not None:
        try:
            await registry.stop_session(sid)
            logger.info(
                "sessions.delete: stopped RuntimeSession {} (client={})",
                sid, client_id,
            )
        except Exception as exc:
            logger.warning(
                "sessions.delete: error stopping RuntimeSession {}: {}",
                sid, exc,
            )

    # 2. Destroy sandbox (client-scoped: Phase 30)
    state = getattr(bridge_module, "_state", None)
    if state is not None:
        try:
            state.destroy_sandbox(session_key, client_id=client_id)
        except Exception as exc:
            logger.warning(
                "sessions.delete: error destroying sandbox for {} (client={}): {}",
                session_key, client_id, exc,
            )

    # 3. Remove disk files (client-scoped)
    sm = _get_session_manager()
    try:
        disk_deleted = sm.delete(session_key, client_id=client_id)
    except OwnershipError as exc:
        raise AppServerError(exc.args[0], code=exc.code) from exc

    # Success if runtime was stopped (session may not have been on disk)
    deleted = runtime_was_active or disk_deleted

    logger.info(
        "sessions.delete: {} (key={}, client={})",
        "deleted" if deleted else "not found",
        session_key, client_id,
    )

    return {"result": {"deleted": deleted}}


# ── sessions.archive ───────────────────────────────────────────────────────


async def sessions_archive_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Archive a session: stop RuntimeSession, clean sandbox, mark archived."""
    typed = validate_session_params("sessions.archive", params)
    session_key = typed.session_key

    import miqi.bridge.server as bridge_module

    sid = _client_session_id(client_id, session_key)

    # 1. Stop RuntimeSession if active
    runtime = await registry.get_session(client_id, sid)
    if runtime is not None:
        try:
            await registry.stop_session(sid)
            logger.info(
                "sessions.archive: stopped RuntimeSession {} (client={})",
                sid, client_id,
            )
        except Exception as exc:
            logger.warning(
                "sessions.archive: error stopping RuntimeSession {}: {}",
                sid, exc,
            )

    # 2. Destroy sandbox (client-scoped: Phase 30)
    state = getattr(bridge_module, "_state", None)
    if state is not None:
        try:
            state.destroy_sandbox(session_key, client_id=client_id)
        except Exception as exc:
            logger.warning(
                "sessions.archive: error destroying sandbox for {} (client={}): {}",
                session_key, client_id, exc,
            )

    # 3. Mark archived on disk (client-scoped)
    sm = _get_session_manager()
    try:
        sm.archive(session_key, client_id=client_id)
    except OwnershipError as exc:
        raise AppServerError(exc.args[0], code=exc.code) from exc

    return {"result": {"archived": True}}


# ── sessions.unarchive ─────────────────────────────────────────────────────


async def sessions_unarchive_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Unarchive a session — restore it to the default session list."""
    typed = validate_session_params("sessions.unarchive", params)
    session_key = typed.session_key

    sm = _get_session_manager()
    try:
        sm.unarchive(session_key, client_id=client_id)
    except OwnershipError as exc:
        raise AppServerError(exc.args[0], code=exc.code) from exc

    return {"result": {"unarchived": True}}


# ── sessions.list_archived ─────────────────────────────────────────────────


async def sessions_list_archived_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """List only archived sessions (client-scoped)."""
    validate_session_params("sessions.list_archived", params)

    from miqi.session.manager import safe_filename

    sm = _get_session_manager()
    sessions = sm.list_sessions(include_archived=True, client_id=client_id)

    # Filter to only archived ones (already client-scoped by list_sessions)
    archived = []
    for s in sessions:
        safe_key = safe_filename(s["key"].replace(":", "_"))
        marker = sm.sessions_dir / safe_key / ".archived"
        if marker.exists():
            archived.append(s)

    return {"result": {"sessions": archived}}


# ── sessions.get_tracked_files ─────────────────────────────────────────────


async def sessions_get_tracked_files_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Return tracked files for a session from tracked_files.json (client-scoped)."""
    typed = validate_session_params("sessions.get_tracked_files", params)
    session_key = typed.session_key

    sm = _get_session_manager()
    try:
        files = sm.load_tracked_files(session_key, client_id=client_id)
    except OwnershipError as exc:
        raise AppServerError(exc.args[0], code=exc.code) from exc
    result = [
        {"path": path, **info}
        for path, info in files.items()
    ]

    return {"result": {"tracked_files": result}}


# ── sessions.clear_tracked_files ───────────────────────────────────────────


async def sessions_clear_tracked_files_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Remove all tracked file entries for a session (client-scoped)."""
    typed = validate_session_params("sessions.clear_tracked_files", params)
    session_key = typed.session_key

    sm = _get_session_manager()
    try:
        sm.clear_tracked_files(session_key, client_id=client_id)
    except OwnershipError as exc:
        raise AppServerError(exc.args[0], code=exc.code) from exc

    return {"result": {"cleared": True}}


# ── sessions.claim_legacy ──────────────────────────────────────────────────


async def sessions_claim_legacy_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Explicitly claim an unowned legacy session.

    This is the ONLY way to take ownership of a legacy session that
    lacks owner_client_id metadata. Once claimed, the session is
    permanently owned by the claiming client.

    A session that is already owned by a different client cannot be
    claimed — it will return UNAUTHORIZED.
    """
    typed = validate_session_params("sessions.claim_legacy", params)
    session_key = typed.session_key

    sm = _get_session_manager()
    try:
        claimed = sm.claim_session(session_key, client_id)
        return {"result": {"claimed": True, "was_already_claimed": not claimed}}
    except OwnershipError as exc:
        raise AppServerError(exc.args[0], code=exc.code) from exc
