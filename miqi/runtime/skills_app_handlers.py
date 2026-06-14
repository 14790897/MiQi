"""Codex-style skills and hooks AppServer handlers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from miqi.runtime.app_server import AppServer, AppServerError, get_bridge_context


def register_skills_app_handlers(server: AppServer) -> None:
    async def _skills_list(request_id, params, client_id, session_id, registry):
        from miqi.agent.skills import SkillsLoader

        roots = [Path(p) for p in get_bridge_context(registry, "skills_extra_roots", [])]
        cwds = params.get("cwds") or params.get("cwd") or []
        if isinstance(cwds, str):
            cwds = [cwds]
        if not cwds:
            state = get_bridge_context(registry, "state", None)
            if state is not None:
                cwds = [str(state.load_config().workspace_path)]
        result = []
        seen: set[str] = set()
        for cwd_raw in cwds:
            cwd = Path(cwd_raw)
            loader = SkillsLoader(workspace=cwd)
            for skill in loader.list_skills(filter_unavailable=False):
                if skill["name"] in seen:
                    continue
                seen.add(skill["name"])
                result.append({
                    "name": skill["name"],
                    "path": skill["path"],
                    "source": skill["source"],
                    "description": loader._get_skill_description(skill["name"]),
                    "available": loader._check_requirements(loader._get_skill_meta(skill["name"])),
                })
            for root in roots:
                if not root.exists():
                    continue
                for skill_dir in root.iterdir():
                    skill_md = skill_dir / "SKILL.md"
                    if not skill_dir.is_dir() or not skill_md.exists():
                        continue
                    if skill_dir.name in seen:
                        continue
                    seen.add(skill_dir.name)
                    result.append({
                        "name": skill_dir.name,
                        "path": str(skill_md),
                        "source": "extraRoot",
                        "description": skill_dir.name,
                        "available": True,
                    })
        result.sort(key=lambda s: s["name"])
        return {"result": {"skills": result}}

    async def _extra_roots_set(request_id, params, client_id, session_id, registry):
        roots = [Path(str(root)).resolve() for root in params.get("roots", [])]
        registry.bridge_context["skills_extra_roots"] = roots
        await server.emit_event(
            session_id or "process",
            "skills/changed",
            {"roots": [str(root) for root in roots]},
            request_id=request_id,
        )
        sink = server._event_sinks.get(client_id)
        if sink is not None:
            await sink({"request_id": request_id, "event": "skills/changed", "data": {"roots": [str(root) for root in roots]}})
        return {"result": {}}

    async def _hooks_list(request_id, params, client_id, session_id, registry):
        cwds = params.get("cwds") or []
        if isinstance(cwds, str):
            cwds = [cwds]
        hooks = []
        for cwd_raw in cwds:
            path = Path(cwd_raw) / ".miqi" / "hooks" / "hooks.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data.get("hooks", []) if isinstance(data, dict) else data
            for entry in entries:
                if isinstance(entry, dict):
                    hooks.append({"cwd": str(cwd_raw), **entry})
        return {"result": {"hooks": hooks}}

    server.register_method("skills/list", _skills_list)
    server.register_method("skills/extraRoots/set", _extra_roots_set)
    server.register_method("hooks/list", _hooks_list)
