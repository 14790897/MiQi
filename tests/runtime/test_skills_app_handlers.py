from pathlib import Path
from unittest.mock import MagicMock

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.skills_app_handlers import register_skills_app_handlers


def write_skill(root: Path, name: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} skill\n---\n# {name}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_skills_list_reads_cwd_and_extra_roots(tmp_path):
    cwd = tmp_path / "workspace"
    extra = tmp_path / "extra"
    (cwd / "skills").mkdir(parents=True)
    write_skill(cwd / "skills", "workspace-skill")
    write_skill(extra, "extra-skill")

    registry = ClientSessionRegistry()
    state = MagicMock()
    cfg = MagicMock()
    cfg.workspace_path = cwd
    state.load_config.return_value = cfg
    registry.bridge_context["state"] = state
    registry.bridge_context["skills_extra_roots"] = [extra]
    server = AppServer(registry)
    register_skills_app_handlers(server)

    response = await server.dispatch(
        "1", "skills/list", {"cwds": [str(cwd)], "forceReload": True}, "client-1", None
    )
    names = {skill["name"] for skill in response["result"]["skills"]}
    assert "workspace-skill" in names
    assert "extra-skill" in names


@pytest.mark.asyncio
async def test_skills_extra_roots_set_updates_process_state_and_emits_event(tmp_path):
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    events = []

    async def sink(envelope):
        events.append(envelope)

    server.set_event_sink("client-1", sink)
    register_skills_app_handlers(server)
    response = await server.dispatch(
        "1", "skills/extraRoots/set", {"roots": [str(tmp_path / "extra")]}, "client-1", None
    )
    assert response["result"] == {}
    assert registry.bridge_context["skills_extra_roots"] == [tmp_path / "extra"]
    assert any(event["event"] == "skills/changed" for event in events)


@pytest.mark.asyncio
async def test_hooks_list_reads_workspace_hooks(tmp_path):
    cwd = tmp_path / "workspace"
    hooks_dir = cwd / ".miqi" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "hooks.json").write_text(
        '{"hooks":[{"name":"pre-tool","event":"pre_tool"}]}',
        encoding="utf-8",
    )
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_skills_app_handlers(server)
    response = await server.dispatch(
        "1", "hooks/list", {"cwds": [str(cwd)]}, "client-1", None
    )
    assert response["result"]["hooks"][0]["name"] == "pre-tool"
