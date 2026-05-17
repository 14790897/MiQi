"""Memory tool — save/update persistent facts about the environment or user."""

from __future__ import annotations

from pathlib import Path

from miqi.agent.tools.base import Tool


class MemoryTool(Tool):
    """Tool for saving and managing persistent memory facts."""

    VALID_TARGETS = {"memory", "user"}

    def __init__(self, memory_store):
        self._store = memory_store

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Save or update persistent facts about the environment or the user. "
            "Use this proactively whenever you learn something durable — project "
            "conventions, user preferences, recurring corrections. Do NOT save "
            "task progress or ephemeral details."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "replace", "remove"],
                    "description": "add (append new fact), replace (update existing), or remove (delete a fact)",
                },
                "target": {
                    "type": "string",
                    "enum": ["memory", "user"],
                    "description": "memory=MEMORY.md (project facts), user=USER.md (user profile)",
                },
                "content": {
                    "type": "string",
                    "description": "The fact to add. Write as a declarative bullet: '- Fact here'",
                },
                "old_text": {
                    "type": "string",
                    "description": "Exact text to replace or remove (required for replace/remove actions)",
                },
            },
            "required": ["action", "target"],
        }

    async def execute(
        self,
        action: str,
        target: str,
        content: str = "",
        old_text: str = "",
    ) -> str:
        if target not in self.VALID_TARGETS:
            return f"Error: invalid target '{target}'. Valid targets are: {', '.join(sorted(self.VALID_TARGETS))}"
        file_path = self._get_path(target)

        if action == "add":
            return self._do_add(file_path, content)
        elif action == "replace":
            return self._do_replace(file_path, old_text, content)
        elif action == "remove":
            return self._do_remove(file_path, old_text)
        else:
            return f"Error: unknown action '{action}'"

    def _get_path(self, target: str) -> Path:
        if target == "user":
            return self._store.memory_dir / "USER.md"
        return self._store.memory_dir / "MEMORY.md"

    def _do_add(self, file_path: Path, content: str) -> str:
        if not content.strip():
            return "Error: 'content' is required for add action"
        existing = ""
        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")
        else:
            header = ""
            if file_path.name == "MEMORY.md":
                header = "# Memory\n\n"
            elif file_path.name == "USER.md":
                header = "# User Profile\n\n"
            existing = header
        new_content = existing.rstrip("\n") + "\n" + content.strip() + "\n"
        if file_path.name == "MEMORY.md":
            self._store.write_memory_md(new_content)
        else:
            self._store.write_user_md(new_content)
        return '{"ok": true, "action": "add", "target": "' + file_path.stem.lower() + '"}'

    def _do_replace(self, file_path: Path, old_text: str, content: str) -> str:
        if not old_text:
            return "Error: 'old_text' is required for replace action"
        if not content.strip():
            return "Error: 'content' is required for replace action"
        if not file_path.exists():
            return f"Error: file {file_path} does not exist"
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: 'old_text' not found in {file_path.name}"
        new_text = text.replace(old_text, content, 1)
        if file_path.name == "MEMORY.md":
            self._store.write_memory_md(new_text)
        else:
            self._store.write_user_md(new_text)
        return '{"ok": true, "action": "replace", "target": "' + file_path.stem.lower() + '"}'

    def _do_remove(self, file_path: Path, old_text: str) -> str:
        if not old_text:
            return "Error: 'old_text' is required for remove action"
        if not file_path.exists():
            return f"Error: file {file_path} does not exist"
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: 'old_text' not found in {file_path.name}"
        lines = text.split("\n")
        new_lines = [line for line in lines if old_text.strip() not in line]
        new_content = "\n".join(new_lines)
        if file_path.name == "MEMORY.md":
            self._store.write_memory_md(new_content)
        else:
            self._store.write_user_md(new_content)
        return '{"ok": true, "action": "remove", "target": "' + file_path.stem.lower() + '"}'
