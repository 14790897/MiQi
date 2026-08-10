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

    # The skill inventory section must be present with the skill name.
    assert "Local Skills" in system_prompt
    assert "demo-agent" in system_prompt

    # The no-denial rule must be present so the model verifies before denying.
    assert "Never claim a skill does not exist" in system_prompt


@pytest.mark.asyncio
async def test_task_runner_separator_only_skill_name_not_matched(fake_services):
    """A separator-only skill dir ('---') normalizes to '' and must NOT
    match every message ('' in normalized is always True)."""
    skill_dir = fake_services.workspace / "skills" / "---"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ---\ndescription: separator-only\n---\n\nBody.\n",
        encoding="utf-8",
    )

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(content="hello", thread_id="cli:default"))

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    assert "Matched Local Skill" not in system_prompt


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


def _make_skill_with_triggers(workspace, name: str, triggers: str, body: str) -> None:
    """Create a workspace skill whose frontmatter declares Triggers."""
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill\ntriggers: {triggers}\n---\n\n{body}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_task_runner_trigger_match_preloads_skill(fake_services):
    """Natural language describing the task (not the skill name) preloads SKILL.md.

    Regression for #613 follow-up: '整理一下工作目录' must hit
    workspace-cleanup via its declared Triggers even though the user
    never names the skill.
    """
    _make_skill_with_triggers(
        fake_services.workspace,
        "workspace-cleanup",
        "整理,归类,cleanup",
        "Classify files into artifacts/reports/ and artifacts/scripts/.",
    )

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(
        content="帮我整理一下工作目录，把文件归类",
        thread_id="cli:default",
    ))

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    assert "Matched Local Skill: workspace-cleanup" in system_prompt
    assert "artifacts/reports/" in system_prompt


@pytest.mark.asyncio
async def test_task_runner_trigger_match_ignored_without_triggers(fake_services):
    """Skills without declared Triggers are not trigger-matched (#613 follow-up).

    The message must avoid trigger words of real builtin skills
    (workspace-cleanup: 整理/归类; pptx-generator: 演示文稿/PPT), which are
    scanned alongside the workspace skills.
    """
    _make_skill(
        fake_services.workspace,
        "demo-agent",
        "Demo agent for price synthesis",
        "Run the synthesis pipeline.",
    )

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    # '合成路线分析' is not in demo-agent's Triggers (it has none), so no preload.
    await runner.handle(UserMessage(
        content="帮我做一下合成路线分析",
        thread_id="cli:default",
    ))

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    assert "Matched Local Skill" not in system_prompt


@pytest.mark.asyncio
async def test_task_runner_short_name_common_word_not_matched(fake_services):
    """A short common skill name without Triggers must not match everyday language.

    'weather' is 6 chars, no separator, no Triggers -> skipped in both
    stages, so '今天天气怎么样' must not preload anything.
    """
    _make_skill(
        fake_services.workspace,
        "weather",
        "Weather forecast",
        "Report the weather.",
    )

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(
        content="今天天气怎么样",
        thread_id="cli:default",
    ))

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    assert "Matched Local Skill" not in system_prompt


<<<<<<< HEAD
=======
@pytest.mark.asyncio
async def test_task_runner_preloads_colliding_nested_builtin_by_path(fake_services, monkeypatch):
    """A nested built-in skill with a synthesized display name still preloads.

    list_skills can synthesize a name like 'plugin-foo' when a nested leaf
    'foo' collides with a top-level skill. No 'plugin-foo/SKILL.md' directory
    exists, so loading by name yields nothing; the matcher must hand the
    indexed path to the loader (CodeRabbit review #625).
    """
    # Top-level 'foo' lives in the WORKSPACE skills dir, which list_skills
    # always scans before builtins — so the nested builtin 'foo' collides
    # deterministically regardless of directory iteration order.
    _make_skill(
        fake_services.workspace,
        "foo",
        "Top-level foo",
        "Top foo body.",
    )

    # Builtin skills dir with a nested colliding layout:
    #   builtin/kwp/foo/SKILL.md        (nested 'foo' → synthesized 'kwp-foo')
    builtin_dir = fake_services.workspace / "builtin"
    (builtin_dir / "kwp" / "foo").mkdir(parents=True)
    (builtin_dir / "kwp" / "foo" / "SKILL.md").write_text(
        "---\nname: foo\ndescription: nested foo\n---\n\nNested foo body.\n",
        encoding="utf-8",
    )

    original_init = SkillsLoader.__init__

    def patched_init(self, workspace, builtin_skills_dir=None):
        original_init(self, workspace, builtin_skills_dir or builtin_dir)

    monkeypatch.setattr(SkillsLoader, "__init__", patched_init)

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(
        content="please use kwp-foo for this task",
        thread_id="cli:default",
    ))

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    assert "Matched Local Skill(s): kwp-foo" in system_prompt
    assert "Nested foo body." in system_prompt


@pytest.mark.asyncio
async def test_task_runner_name_and_trigger_hit_both_preload(fake_services):
    """A message naming a skill AND describing another's trigger preloads both.

    Regression: stage-1 name match must not skip stage-2 trigger matching —
    'use demo-agent and organize workspace' should preload demo-agent (by
    name) and workspace-cleanup (by trigger).
    """
    _make_skill(
        fake_services.workspace,
        "demo-agent",
        "Demo agent for price synthesis",
        "Run the synthesis pipeline.",
    )
    _make_skill_with_triggers(
        fake_services.workspace,
        "workspace-cleanup",
        "organize workspace",
        "Classify files into artifacts/reports/ and artifacts/scripts/.",
    )

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(
        content="use demo-agent and organize workspace",
        thread_id="cli:default",
    ))

    system_prompt = fake_services.turn_runner.run.await_args.kwargs["system_prompt"]
    assert "Matched Local Skill(s): demo-agent, workspace-cleanup" in system_prompt
    assert "Run the synthesis pipeline." in system_prompt
    assert "artifacts/reports/" in system_prompt


>>>>>>> 5c018cef (fix(skills): order-independent nested builtin test, both match stages,)
