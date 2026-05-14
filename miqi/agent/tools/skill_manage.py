"""Skill manage tool — create, view, patch, and archive reusable skills."""

from __future__ import annotations

import json
import re
from pathlib import Path

from miqi.agent.skills import SkillsLoader
from miqi.agent.tools.base import Tool


def _set_frontmatter_key(content: str, key: str, value: str) -> str:
    """Add or replace a key in YAML frontmatter using regex (no yaml library)."""
    fm_match = re.match(r"^(---\n)(.*?)(\n---\n)", content, re.DOTALL)
    if not fm_match:
        return f'---\n{key}: "{value}"\n---\n\n{content}'
    prefix, fm_body, suffix = fm_match.group(1), fm_match.group(2), fm_match.group(3)
    rest = content[fm_match.end() :]
    lines = fm_body.split("\n")
    replaced = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}:"):
            new_lines.append(f'{key}: "{value}"')
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f'{key}: "{value}"')
    return prefix + "\n".join(new_lines) + suffix + rest


class SkillManageTool(Tool):
    """Tool for managing reusable skills (procedural workflows)."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._skills = SkillsLoader(workspace)

    @property
    def name(self) -> str:
        return "skill_manage"

    @property
    def description(self) -> str:
        return (
            "Manage reusable skills (procedural workflows). "
            "Create a skill after completing any complex task with 5+ tool calls. "
            "Patch a skill immediately if you notice it is outdated or wrong during use."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "view", "create", "patch", "archive"],
                    "description": "list all skills, view a skill, create a new skill, patch an existing skill, or archive a skill",
                },
                "name": {
                    "type": "string",
                    "description": "Skill name (required for view/create/patch/archive)",
                },
                "content": {
                    "type": "string",
                    "description": "Full SKILL.md content (required for create). Must include YAML frontmatter with description and version.",
                },
                "patch_text": {
                    "type": "string",
                    "description": "Text to append to the skill (required for patch)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        name: str = "",
        content: str = "",
        patch_text: str = "",
    ) -> str:
        if action == "list":
            return self._do_list()
        elif action == "view":
            return self._do_view(name)
        elif action == "create":
            return self._do_create(name, content)
        elif action == "patch":
            return self._do_patch(name, patch_text)
        elif action == "archive":
            return self._do_archive(name)
        else:
            return f"Error: unknown action '{action}'"

    def _do_list(self) -> str:
        skills = self._skills.list_skills(filter_unavailable=False)
        results = []
        for s in skills:
            results.append(
                {
                    "name": s["name"],
                    "description": self._skills._get_skill_description(s["name"]),
                    "source": s["source"],
                }
            )
        return json.dumps({"skills": results}, ensure_ascii=False)

    def _do_view(self, name: str) -> str:
        if not name:
            return "Error: 'name' is required for view action"
        content = self._skills.load_skill(name)
        if content is None:
            return f"Error: skill '{name}' not found"
        return content

    def _do_create(self, name: str, content: str) -> str:
        if not name:
            return "Error: 'name' is required for create action"
        if not content.strip():
            return "Error: 'content' is required for create action"

        # Only allow creation in workspace skills
        skill_dir = self.workspace / "skills" / name
        if skill_dir.exists():
            return f"Error: skill '{name}' already exists"

        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content.strip() + "\n", encoding="utf-8")
        return f'{{"ok": true, "action": "create", "name": "{name}"}}'

    def _do_patch(self, name: str, patch_text: str) -> str:
        if not name:
            return "Error: 'name' is required for patch action"
        if not patch_text.strip():
            return "Error: 'patch_text' is required for patch action"

        # Only allow patching workspace skills
        workspace_skill = self.workspace / "skills" / name / "SKILL.md"
        if not workspace_skill.exists():
            return f"Error: skill '{name}' not found in workspace (cannot patch built-in skills)"

        existing = workspace_skill.read_text(encoding="utf-8")
        new_content = existing.rstrip("\n") + "\n\n" + patch_text.strip() + "\n"
        workspace_skill.write_text(new_content, encoding="utf-8")
        return f'{{"ok": true, "action": "patch", "name": "{name}"}}'

    def _do_archive(self, name: str) -> str:
        if not name:
            return "Error: 'name' is required for archive action"

        # Only allow archiving workspace skills
        workspace_skill = self.workspace / "skills" / name / "SKILL.md"
        if not workspace_skill.exists():
            return f"Error: skill '{name}' not found in workspace (cannot archive built-in skills)"

        content = workspace_skill.read_text(encoding="utf-8")
        new_content = _set_frontmatter_key(content, "archived", "true")
        workspace_skill.write_text(new_content, encoding="utf-8")
        return f'{{"ok": true, "action": "archive", "name": "{name}"}}'
