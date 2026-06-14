"""Skill handlers for AppServer dispatch.

Phase 35.5: Migrates skills.list, skills.get, skills.open_folder,
skills.create, skills.upload, and skills.delete from bridge legacy
handlers to AppServer async handlers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError

_SKILL_NAME_RE = re.compile(r'^[a-z][a-z0-9-]*$')


def _get_skills_loader() -> Any:
    """Get a SkillsLoader for the current workspace."""
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()
    from miqi.agent.skills import SkillsLoader
    return SkillsLoader(workspace=config.workspace_path)


async def skills_list_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """List all skills with availability info and missing requirements."""
    loader = _get_skills_loader()
    all_skills = loader.list_skills(filter_unavailable=False)
    result = []
    for s in all_skills:
        meta = loader._get_skill_meta(s["name"])
        desc = loader._get_skill_description(s["name"])
        available = loader._check_requirements(meta)
        missing = loader._get_missing_requirements(meta) if not available else None
        result.append({
            "name": s["name"],
            "source": s["source"],
            "path": s["path"],
            "description": desc,
            "available": available,
            "missingRequirements": missing,
        })
    result.sort(key=lambda x: (0 if x["available"] else 1, x["name"]))
    return {"result": {"skills": result}}


async def skills_get_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Get detailed skill info with content and metadata."""
    name = params.get("name", "").strip()
    if not name:
        raise AppServerError("name is required", code="INVALID_PARAMS")

    loader = _get_skills_loader()
    content = loader.load_skill(name)
    if content is None:
        raise AppServerError(f"Skill not found: {name}", code="NOT_FOUND")

    skill_info = None
    for s in loader.list_skills(filter_unavailable=False):
        if s["name"] == name:
            skill_info = s
            break

    meta = loader._get_skill_meta(name)
    available = loader._check_requirements(meta)
    missing = loader._get_missing_requirements(meta) if not available else None
    metadata = loader.get_skill_metadata(name)

    return {"result": {
        "name": name,
        "source": skill_info["source"] if skill_info else "unknown",
        "path": skill_info["path"] if skill_info else "",
        "description": loader._get_skill_description(name),
        "available": available,
        "missingRequirements": missing,
        "content": content,
        "metadata": metadata,
    }}


async def skills_open_folder_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Return the skill's folder path for the Desktop to open.

    This handler does NOT launch a GUI app — it returns a structured
    result with the folder path that the Desktop can act on.
    """
    name = params.get("name", "").strip()
    if not name:
        raise AppServerError("name is required", code="INVALID_PARAMS")

    loader = _get_skills_loader()
    skill_path = loader.get_skill_path(name)
    if skill_path is None:
        raise AppServerError(f"Skill not found: {name}", code="NOT_FOUND")

    folder = str(skill_path.parent if skill_path.is_file() else skill_path)
    return {"result": {"opened": True, "path": folder}}


async def skills_create_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Create a blank workspace skill."""
    name = str(params.get("name", "")).strip()
    description = str(params.get("description", "")).strip()
    if not name or not _SKILL_NAME_RE.match(name):
        raise AppServerError(
            "Invalid name — use lowercase letters, digits, hyphens",
            code="INVALID_PARAMS",
        )

    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()

    skill_dir = config.workspace_path / "skills" / name
    if skill_dir.exists():
        raise AppServerError(
            f"Skill '{name}' already exists", code="INVALID_PARAMS",
        )

    skill_dir.mkdir(parents=True)
    template = (
        f"---\n"
        f"name: {name}\n"
        f"description: {description or 'A new skill'}\n"
        f'version: "1.0"\n'
        f"---\n\n"
        f"# {name}\n\n{description or 'A new skill'}\n"
    )
    (skill_dir / "SKILL.md").write_text(template, encoding="utf-8")
    return {"result": {"ok": True, "path": str(skill_dir)}}


async def skills_upload_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Save uploaded YAML content as a new workspace skill."""
    name = str(params.get("name", "")).strip()
    content = str(params.get("content", "")).strip()
    if not name or not content:
        raise AppServerError(
            "name and content are required", code="INVALID_PARAMS",
        )

    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()

    skill_dir = config.workspace_path / "skills" / name
    if skill_dir.exists():
        raise AppServerError(
            f"Skill '{name}' already exists", code="INVALID_PARAMS",
        )

    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return {"result": {"ok": True}}


async def skills_delete_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Delete a workspace skill. Builtin skills cannot be deleted."""
    import shutil as _shutil

    name = str(params.get("name", "")).strip()

    builtin_dir = Path(__file__).parent.parent / "skills"
    if (builtin_dir / name).exists():
        raise AppServerError(
            "Builtin skills cannot be deleted", code="INVALID_PARAMS",
        )

    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()

    skill_dir = config.workspace_path / "skills" / name
    if not skill_dir.exists():
        raise AppServerError(
            f"Skill '{name}' not found in workspace", code="NOT_FOUND",
        )

    _shutil.rmtree(skill_dir)
    return {"result": {"ok": True}}
