"""SkillCurator — LLM-driven lifecycle management for workspace skills."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

SKILL_USAGE_FILE = "SKILL_USAGE.json"

SKILL_CURATOR_SYSTEM_PROMPT = """You are a skill curator. Your task is to find redundant or overlapping workspace skills \
and suggest merges.

Given a list of skills in the format:
  [name] description

Identify groups of skills that serve the same or very similar purpose. \
For each group, choose the best representative name and write a merged description.

Return ONLY a JSON array of objects:
  {"keep_name": "<name>", "merge_names": ["<name2>", "<name3>"], \
"merged_description": "<merged description>"}

Do NOT include skills that have no similar peers. Do NOT merge skills with clearly different purposes."""


@dataclass
class SkillCuratorReport:
    merged_count: int
    archived_count: int
    run_at: str


class SkillCurator:
    """LLM-driven skill deduplication and lifecycle management.

    Called periodically via the runtime nudge/flush mechanism. Manages workspace
    skills only (never touches built-in skills).
    (Historical: previously called from AgentLoop.flush_if_needed().)
    """

    STALE_DAYS = 60      # unused for 60 days → stale
    ARCHIVE_DAYS = 90    # stale for 30 more days → archived

    def __init__(
        self,
        workspace: Path,
        llm_call: Callable[..., Awaitable[Any]],
        *,
        enabled: bool = True,
        interval_days: int = 7,
        review_threshold: int = 20,
        model: str = "",
    ):
        self._workspace = workspace
        self._memory_dir = workspace / "memory"
        self._skills_dir = workspace / "skills"
        self._llm_call = llm_call
        self.enabled = enabled
        self.interval_days = max(1, interval_days)
        self.review_threshold = max(1, review_threshold)
        self.model = model

    @property
    def _usage_file(self) -> Path:
        return self._memory_dir / SKILL_USAGE_FILE

    def _load_usage(self) -> dict[str, dict]:
        if not self._usage_file.exists():
            return {}
        try:
            return json.loads(self._usage_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_usage(self, usage: dict) -> None:
        self._usage_file.parent.mkdir(parents=True, exist_ok=True)
        self._usage_file.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_use(self, name: str) -> None:
        """Record that a skill was used."""
        if not self.enabled:
            return
        usage = self._load_usage()
        entry = usage.get(name, {"use_count": 0, "patch_count": 0, "last_used_at": "", "first_seen_at": datetime.now().isoformat()})
        entry["use_count"] = entry.get("use_count", 0) + 1
        entry["last_used_at"] = datetime.now().isoformat()
        if not entry.get("first_seen_at"):
            entry["first_seen_at"] = entry["last_used_at"]
        usage[name] = entry
        self._save_usage(usage)

    def record_patch(self, name: str) -> None:
        """Record that a skill was patched."""
        if not self.enabled:
            return
        usage = self._load_usage()
        entry = usage.get(name, {"use_count": 0, "patch_count": 0, "last_used_at": "", "first_seen_at": datetime.now().isoformat()})
        entry["patch_count"] = entry.get("patch_count", 0) + 1
        entry["last_used_at"] = datetime.now().isoformat()
        if not entry.get("first_seen_at"):
            entry["first_seen_at"] = entry["last_used_at"]
        usage[name] = entry
        self._save_usage(usage)

    def update_lifecycle(self) -> int:
        """Advance skill lifecycle states based on idle time. Returns changed count."""
        if not self.enabled or not self._skills_dir.exists():
            return 0

        usage = self._load_usage()
        now = datetime.now()
        changed = 0

        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            name = skill_dir.name
            meta = self._read_frontmatter(skill_file)
            if not meta:
                continue

            # Pinned skills are exempt
            pinned = meta.get("pinned")
            if pinned is True or (isinstance(pinned, str) and pinned.lower() == "true"):
                continue

            current_state = str(meta.get("state", "active"))

            # Already archived
            if current_state == "archived":
                continue

            # Compute idle days from usage tracking, fallback to frontmatter dates
            u_entry = usage.get(name)
            last_used_str = ""
            if u_entry and u_entry.get("last_used_at"):
                last_used_str = u_entry["last_used_at"]
            else:
                last_used_str = str(meta.get("last_used_at", ""))

            idle_days = 0.0
            if last_used_str:
                try:
                    dt = datetime.fromisoformat(last_used_str)
                    idle_days = max(0.0, (now - dt).total_seconds() / 86400)
                except ValueError:
                    pass

            new_state = current_state
            if current_state == "active" and idle_days >= self.ARCHIVE_DAYS:
                new_state = "archived"
            elif current_state == "active" and idle_days >= self.STALE_DAYS:
                new_state = "stale"
            elif current_state == "stale" and idle_days >= self.ARCHIVE_DAYS:
                new_state = "archived"

            if new_state != current_state:
                content = skill_file.read_text(encoding="utf-8")
                content = self._set_frontmatter_key(content, "state", new_state)
                if new_state == "archived":
                    content = self._set_frontmatter_key(content, "archived", "true")
                skill_file.write_text(content, encoding="utf-8")
                changed += 1

        return changed

    async def maybe_run(self, force: bool = False) -> SkillCuratorReport | None:
        """Check state and run curator lifecycle update + optional LLM review."""
        if not self.enabled:
            return None

        changed = self.update_lifecycle()

        # Run LLM review when workspace skill count exceeds threshold
        merged_count = 0
        if self._skills_dir.exists():
            skill_count = sum(1 for d in self._skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
            if skill_count >= self.review_threshold:
                try:
                    merged_count = await self._run_llm_review()
                except Exception:
                    pass

        now = datetime.now().isoformat()
        return SkillCuratorReport(
            merged_count=merged_count,
            archived_count=changed,
            run_at=now,
        )

    async def _run_llm_review(self) -> int:
        """Run LLM review to identify duplicate skills. Returns number merged."""
        if not self._skills_dir.exists():
            return 0

        skills = []
        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            meta = self._read_frontmatter(skill_file)
            pinned = meta.get("pinned") if meta else None
            if pinned is True or (isinstance(pinned, str) and pinned.lower() == "true"):
                continue
            archived = meta.get("archived") if meta else None
            if archived is True or (isinstance(archived, str) and archived.lower() == "true"):
                continue
            desc = meta.get("description", skill_dir.name) if meta else skill_dir.name
            skills.append(f"[{skill_dir.name}] {desc}")

        if len(skills) < 2:
            return 0

        try:
            response = await self._llm_call(
                messages=[
                    {"role": "system", "content": SKILL_CURATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": "\n".join(skills)},
                ],
                tools=None,
                model=self.model,
                max_tokens=4096,
                temperature=0.3,
            )
        except Exception:
            return 0

        content = self._extract_content(response)
        merges = self._parse_merges(content)
        if not merges:
            return 0

        merged = 0
        for merge in merges:
            keep_name = merge.get("keep_name", "")
            merge_names = merge.get("merge_names", [])
            if not keep_name or not merge_names:
                continue

            for mname in merge_names:
                mdir = self._skills_dir / mname
                if mdir.is_dir() and (mdir / "SKILL.md").exists():
                    skill_content = (mdir / "SKILL.md").read_text(encoding="utf-8")
                    skill_content = self._set_frontmatter_key(skill_content, "archived", "true")
                    skill_content = self._set_frontmatter_key(skill_content, "state", "archived")
                    (mdir / "SKILL.md").write_text(skill_content, encoding="utf-8")
                    merged += 1

            # Update keep skill's description
            kdir = self._skills_dir / keep_name
            if kdir.is_dir() and (kdir / "SKILL.md").exists() and merge.get("merged_description"):
                keep_content = (kdir / "SKILL.md").read_text(encoding="utf-8")
                keep_content = self._set_frontmatter_key(
                    keep_content, "description", merge["merged_description"]
                )
                (kdir / "SKILL.md").write_text(keep_content, encoding="utf-8")

        return merged

    @staticmethod
    def _read_frontmatter(file_path: Path) -> dict | None:
        if not file_path.exists():
            return None
        content = file_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None
        metadata = {}
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                raw = value.strip().strip("\"'")
                if raw.lower() in ("true", "yes"):
                    metadata[key.strip()] = True
                elif raw.lower() in ("false", "no"):
                    metadata[key.strip()] = False
                else:
                    metadata[key.strip()] = raw
        return metadata

    @staticmethod
    def _set_frontmatter_key(content: str, key: str, value: str) -> str:
        fm_match = re.match(r"^(---\n)(.*?)(\n---\n)", content, re.DOTALL)
        if not fm_match:
            return f'---\n{key}: "{value}"\n---\n\n{content}'
        prefix, fm_body, suffix = fm_match.group(1), fm_match.group(2), fm_match.group(3)
        rest = content[fm_match.end():]
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

    @staticmethod
    def _extract_content(response: Any) -> str:
        if isinstance(response, str):
            return response
        if hasattr(response, "content"):
            return str(response.content) or ""
        return str(response)

    @staticmethod
    def _parse_merges(content: str) -> list[dict[str, Any]]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
        return []
