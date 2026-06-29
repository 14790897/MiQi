"""Cron handlers for AppServer dispatch.

Phase 35.6: Migrates cron.list, cron.create, cron.update, cron.delete,
cron.toggle, cron.run, and cron.runs from bridge legacy handlers to
AppServer async handlers. cron.run uses the persistent event loop
instead of asyncio.run().
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError


def _get_cron_service() -> Any:
    """Create a CronService pointed at the standard data dir."""
    import miqi.bridge.server as bridge_module
    from miqi.config.loader import get_data_dir
    from miqi.cron.service import CronService

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()
    store_path = get_data_dir() / "cron" / "jobs.json"
    return CronService(store_path, job_timeout=config.cron.job_timeout_seconds)


def _job_to_dict(job: Any) -> dict[str, Any]:
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


# ── cron.list ────────────────────────────────────────────────────────────────


async def cron_list_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """List all cron jobs."""
    service = _get_cron_service()
    jobs = service.list_jobs(include_disabled=True)
    return {"result": {"jobs": [_job_to_dict(j) for j in jobs]}}


# ── cron.create ──────────────────────────────────────────────────────────────


async def cron_create_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Create a new cron job."""
    from miqi.cron.types import CronSchedule

    name = params.get("name", "").strip()
    if not name:
        raise AppServerError("name is required", code="INVALID_PARAMS")

    schedule_kind = params.get("scheduleKind", "every")
    if schedule_kind not in ("at", "every", "cron"):
        raise AppServerError(
            f"Invalid schedule kind: {schedule_kind}", code="INVALID_PARAMS",
        )

    try:
        schedule = CronSchedule(kind=schedule_kind)
        if schedule_kind == "at":
            at_ms = params.get("atMs")
            if not at_ms:
                raise AppServerError(
                    "atMs is required for at schedules", code="INVALID_PARAMS",
                )
            schedule.at_ms = int(at_ms)
        elif schedule_kind == "every":
            every_ms = params.get("everyMs")
            if not every_ms:
                raise AppServerError(
                    "everyMs is required for every schedules", code="INVALID_PARAMS",
                )
            schedule.every_ms = int(every_ms)
        elif schedule_kind == "cron":
            expr = params.get("expr", "").strip()
            if not expr:
                raise AppServerError(
                    "expr is required for cron schedules", code="INVALID_PARAMS",
                )
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
        return {"result": {"job": _job_to_dict(job)}}
    except ValueError as exc:
        logger.warning("cron.create: validation error: {}", exc)
        raise AppServerError(
            "Invalid cron job configuration", code="INVALID_PARAMS",
        ) from exc


# ── cron.update ──────────────────────────────────────────────────────────────


async def cron_update_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Update an existing cron job."""
    job_id = params.get("jobId", "").strip()
    if not job_id:
        raise AppServerError("jobId is required", code="INVALID_PARAMS")

    service = _get_cron_service()
    jobs = service.list_jobs(include_disabled=True)
    target = None
    for j in jobs:
        if j.id == job_id:
            target = j
            break

    if target is None:
        raise AppServerError(
            f"Job not found: {job_id}", code="NOT_FOUND",
        )

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
            raise AppServerError(
                f"Invalid schedule kind: {kind}", code="INVALID_PARAMS",
            )
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
            logger.warning("cron.update: schedule validation error: {}", exc)
            raise AppServerError(
                "Invalid schedule configuration", code="INVALID_PARAMS",
            ) from exc

        # Recompute next run
        from miqi.cron.service import _compute_next_run, _now_ms
        target.state.next_run_at_ms = _compute_next_run(target.schedule, _now_ms())

    target.updated_at_ms = int(time.time() * 1000)
    service._save_store()
    return {"result": {"job": _job_to_dict(target)}}


# ── cron.delete ──────────────────────────────────────────────────────────────


async def cron_delete_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Delete a cron job."""
    job_id = params.get("jobId", "").strip()
    if not job_id:
        raise AppServerError("jobId is required", code="INVALID_PARAMS")

    service = _get_cron_service()
    removed = service.remove_job(job_id)
    return {"result": {"deleted": removed}}


# ── cron.toggle ──────────────────────────────────────────────────────────────


async def cron_toggle_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Toggle a cron job enabled/disabled."""
    job_id = params.get("jobId", "").strip()
    if not job_id:
        raise AppServerError("jobId is required", code="INVALID_PARAMS")

    enabled = bool(params.get("enabled", True))
    service = _get_cron_service()
    job = service.enable_job(job_id, enabled=enabled)
    if job is None:
        raise AppServerError(
            f"Job not found: {job_id}", code="NOT_FOUND",
        )
    return {"result": {"job": _job_to_dict(job)}}


# ── cron.run ─────────────────────────────────────────────────────────────────


async def cron_run_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Force-run a cron job.

    Uses the persistent event loop (no asyncio.run()).
    """
    job_id = params.get("jobId", "").strip()
    if not job_id:
        raise AppServerError("jobId is required", code="INVALID_PARAMS")

    service = _get_cron_service()
    ok = await service.run_job(job_id, force=True)
    if not ok:
        raise AppServerError(
            f"Job not found: {job_id}", code="NOT_FOUND",
        )

    # Re-fetch to return updated state
    jobs = service.list_jobs(include_disabled=True)
    for j in jobs:
        if j.id == job_id:
            return {"result": {"job": _job_to_dict(j)}}

    raise AppServerError(
        f"Job disappeared: {job_id}", code="INTERNAL",
    )


# ── cron.runs ────────────────────────────────────────────────────────────────


async def cron_runs_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """List cron job runs."""
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
    return {"result": {"runs": runs}}
