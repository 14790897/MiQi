"""TaskRunner injects the local skill inventory into the system prompt (#613).

Regression test for: local skills were never surfaced to the model on the
desktop runtime path (chat.send -> RuntimeSession.submit -> TaskRunner.handle),
so the model denied the existence of installed skills from training priors
("没有名为 xxx 的现成 Agent") instead of discovering them during planning.

The fix: TaskRunner appends the workspace/builtin skill inventory
(SkillsLoader.build_skills_summary) to the effective system prompt before
handing it to TurnRunner, plus a no-denial rule telling the model to verify
against the list before claiming a skill does not exist.
"""

import asyncio

import pytest

from miqi.agent.skills import SkillsLoader
from miqi.protocol.commands import UserMessage
from miqi.runtime.task_runner import TaskRunner


@pytest.mark.asyncio
async def test_task_runner_injects_local_skill_inventory_into_system_prompt(fake_services):
    """A workspace skill appears by name + description in the turn's system prompt."""
    skill_dir = fake_services.workspace / "skills" / "demo-agent"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo-agent\n"
        "description: Demo agent for price synthesis and feasibility reports\n"
        "---\n"
        "\n"
        "Run the synthesis pipeline: parse DOI, fetch prices, generate report.\n",
        encoding="utf-8",
    )

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(
        content="can the demo-agent generate a feasibility report from a DOI?",
        thread_id="cli:default",
    ))

    assert fake_services.turn_runner.run.await_count == 1
    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]

    # The skill inventory section must be present with name + description.
    assert "Local Skills" in system_prompt
    assert "<name>demo-agent</name>" in system_prompt
    assert "Demo agent for price synthesis and feasibility reports" in system_prompt

    # The no-denial rule must be present so the model verifies before denying.
    assert "Never claim a skill does not exist" in system_prompt


@pytest.mark.asyncio
async def test_task_runner_skill_injection_skips_without_crashing(fake_services):
    """No workspace skills dir -> turn still executes with the base prompt."""
    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(content="hello", thread_id="cli:default"))

    assert fake_services.turn_runner.run.await_count == 1
    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    # Base prompt still present and the turn executed normally.
    assert "MiQi Desktop Agent" in system_prompt


def _make_skill(workspace, name: str, description: str, body: str) -> None:
    """Create a workspace skill at <workspace>/skills/<name>/SKILL.md."""
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_task_runner_preloads_matched_skill_body_on_intent_hit(fake_services):
    """User message naming a local skill preloads its SKILL.md into the prompt."""
    _make_skill(
        fake_services.workspace,
        "demo-agent",
        "Demo agent for price synthesis",
        "Run the synthesis pipeline: parse DOI, fetch prices, generate report.",
    )

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(
        content="can the demo-agent generate a feasibility report from a DOI?",
        thread_id="cli:default",
    ))

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    # The matched skill's full body must be preloaded as context.
    assert "Matched Local Skill: demo-agent" in system_prompt
    assert "Run the synthesis pipeline: parse DOI, fetch prices, generate report." in system_prompt


@pytest.mark.asyncio
async def test_task_runner_intent_match_normalizes_separators(fake_services):
    """'demo agent' (spaces) matches skill 'demo-agent' (hyphens)."""
    _make_skill(
        fake_services.workspace,
        "demo-agent",
        "Demo agent for price synthesis",
        "Run the synthesis pipeline: parse DOI, fetch prices, generate report.",
    )

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(
        content="can the demo agent generate a feasibility report?",
        thread_id="cli:default",
    ))

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    assert "Matched Local Skill: demo-agent" in system_prompt


@pytest.mark.asyncio
async def test_task_runner_intent_hit_logs_and_miss_skips_preload(fake_services, caplog):
    """HIT logs the matched skill; a message without a skill ref preloads nothing."""
    from loguru import logger as loguru_logger

    _make_skill(
        fake_services.workspace,
        "demo-agent",
        "Demo agent for price synthesis",
        "Run the synthesis pipeline: parse DOI, fetch prices, generate report.",
    )

    messages: list[str] = []

    def _sink(message):
        messages.append(str(message.record["message"]))

    handler_id = loguru_logger.add(_sink, level="DEBUG")
    try:
        events = asyncio.Queue()
        runner = TaskRunner(services=fake_services, event_queue=events)

        # HIT: message references the skill by name.
        await runner.handle(UserMessage(
            content="please use demo-agent for this",
            thread_id="cli:default",
        ))
    finally:
        loguru_logger.remove(handler_id)

    assert any("skill index: HIT" in m and "demo-agent" in m for m in messages), (
        f"expected a skill-index HIT log, got: {messages}"
    )

    # MISS: unrelated message -> no preload, no crash.
    messages.clear()
    handler_id = loguru_logger.add(_sink, level="DEBUG")
    try:
        events = asyncio.Queue()
        runner = TaskRunner(services=fake_services, event_queue=events)

        await runner.handle(UserMessage(
            content="what is the weather today?",
            thread_id="cli:default",
        ))
    finally:
        loguru_logger.remove(handler_id)

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    assert "Matched Local Skill" not in system_prompt
    assert any("skill index: MISS" in m for m in messages), (
        f"expected a skill-index MISS log, got: {messages}"
    )


@pytest.mark.asyncio
async def test_task_runner_scans_skills_once_per_turn(fake_services, monkeypatch):
    """Skill discovery scans the filesystem once per turn, not twice (#613).

    The inventory summary and the intent matcher must share a single
    list_skills() pass; a second scan is pure waste on every message.
    """
    _make_skill(
        fake_services.workspace,
        "demo-agent",
        "Demo agent for price synthesis",
        "Run the synthesis pipeline: parse DOI, fetch prices, generate report.",
    )

    calls: list[int] = []
    original = SkillsLoader.list_skills

    def counting_list_skills(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SkillsLoader, "list_skills", counting_list_skills)

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(
        content="please use demo-agent for this",
        thread_id="cli:default",
    ))

    assert fake_services.turn_runner.run.await_count == 1
    assert len(calls) == 1, f"expected exactly 1 skill scan, got {len(calls)}"


