"""Tests for AgentJobRuntime (Phase 13.2)."""

import asyncio

import pytest


@pytest.fixture
def fake_services_for_jobs(fake_services):
    """Services fixture with a working turn_runner.run_agent_job mock."""
    from miqi.runtime.turn_runner import TurnResult

    async def _fake_run_agent_job(job):
        return TurnResult(
            final_content=f"Completed: {job.task}",
            messages=[{"role": "assistant", "content": f"Completed: {job.task}"}],
            tools_used=[],
        )

    fake_services.turn_runner.run_agent_job = _fake_run_agent_job
    return fake_services


@pytest.mark.asyncio
async def test_agent_job_runtime_starts_job(fake_services_for_jobs):
    from miqi.runtime.agent_jobs import AgentJobRuntime

    runtime = AgentJobRuntime(services=fake_services_for_jobs)

    job = await runtime.start(
        agent_type="code-agent",
        task="inspect repo",
        parent_thread_id="main",
    )

    assert job.job_id
    assert job.thread_id
    assert job.thread_id == f"{fake_services_for_jobs.session_id}:{job.job_id}"
    assert job.status in {"queued", "running"}


@pytest.mark.asyncio
async def test_agent_job_runtime_lists_jobs(fake_services_for_jobs):
    from miqi.runtime.agent_jobs import AgentJobRuntime

    runtime = AgentJobRuntime(services=fake_services_for_jobs)
    job = await runtime.start(
        agent_type="code-agent", task="inspect repo", parent_thread_id="main",
    )

    jobs = runtime.list()
    assert any(item["job_id"] == job.job_id for item in jobs)


@pytest.mark.asyncio
async def test_agent_job_completes_and_persists_result(fake_services_for_jobs):
    from miqi.runtime.agent_jobs import AgentJobRuntime

    runtime = AgentJobRuntime(services=fake_services_for_jobs)
    job = await runtime.start(
        agent_type="code-agent", task="analyze me", parent_thread_id="main",
    )

    # Let the background task run
    await asyncio.sleep(0.1)

    # Job should have completed
    jobs = runtime.list()
    found = next(item for item in jobs if item["job_id"] == job.job_id)
    assert found["status"] == "completed"
    assert found["result_preview"]


@pytest.mark.asyncio
async def test_agent_job_get_raises_for_unknown():
    from miqi.runtime.agent_jobs import AgentJobRuntime

    runtime = AgentJobRuntime(services=None)
    with pytest.raises(KeyError):
        runtime.get("nonexistent")


@pytest.mark.asyncio
async def test_agent_job_kill_aborts_running_job(fake_services_for_jobs):
    from miqi.runtime.agent_jobs import AgentJobRuntime

    # Use a blocking turn runner so the job stays "running"
    async def _blocking(_job):
        await asyncio.sleep(10)
        from miqi.runtime.turn_runner import TurnResult
        return TurnResult(final_content="done", messages=[], tools_used=[])

    fake_services_for_jobs.turn_runner.run_agent_job = _blocking

    runtime = AgentJobRuntime(services=fake_services_for_jobs)
    job = await runtime.start(
        agent_type="code-agent", task="long task", parent_thread_id="main",
    )

    # Give the task a tick to start
    await asyncio.sleep(0.02)

    # Kill it
    await runtime.kill(job.job_id)

    # Give cancellation a tick
    await asyncio.sleep(0.05)

    jobs = runtime.list()
    found = next(item for item in jobs if item["job_id"] == job.job_id)
    assert found["status"] == "aborted"


def test_agent_job_dataclass_defaults():
    from miqi.runtime.agent_jobs import AgentJob

    job = AgentJob(
        job_id="j1",
        agent_type="code-agent",
        task="test",
        thread_id="t1",
        parent_thread_id="main",
    )
    assert job.status == "queued"
    assert job.result is None
    assert job.error is None
    assert job.completed_at is None
    assert job.created_at > 0
