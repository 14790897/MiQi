"""Skills loader for agent capabilities."""

import json
import os
import re
import shutil
from pathlib import Path

# Default builtin skills directory (relative to this file)
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    Loader for agent skills.

    Skills are markdown files (SKILL.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
        # Per-instance metadata cache: frontmatter is read at most once per
        # loader. The runtime creates a fresh loader each turn, so the cache
        # cannot go stale across turns (#613).
        self._meta_cache: dict[str, dict | None] = {}

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        List all available skills.

        Args:
            filter_unavailable: If True, filter out skills with unmet requirements.

        Returns:
            List of skill info dicts with 'name', 'path', 'source'.
        """
        skills = []

        # Workspace skills (highest priority)
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append({"name": skill_dir.name, "path": str(skill_file), "source": "workspace"})

        # Built-in skills
        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists() and not any(s["name"] == skill_dir.name for s in skills):
                        skills.append({"name": skill_dir.name, "path": str(skill_file), "source": "builtin"})
                    # Recursively discover nested skills (e.g. kwp/<plugin>/<skill>/SKILL.md)
                    self._discover_nested_skills(skill_dir, skills, source="builtin")

        # Filter out archived skills
        skills = [s for s in skills if not self._is_skill_archived(s["name"])]

        # Filter by requirements
        if filter_unavailable:
            return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
        return skills

    def _discover_nested_skills(
        self, root: Path, skills: list[dict[str, str]], source: str, depth: int = 0
    ) -> None:
        """Recursively discover SKILL.md files at up to 2 levels of nesting.

        Supports directory layouts like:
          kwp/<plugin>/<skill>/SKILL.md
          kwp/<plugin>/SKILL.md
        """
        if depth >= 3:
            return  # Guard against runaway recursion
        names_seen = {s["name"] for s in skills}
        for item in sorted(root.iterdir()):
            if not item.is_dir() or item.name.startswith(".") or item.name == "__pycache__":
                continue
            skill_file = item / "SKILL.md"
            if skill_file.exists():
                skill_name = item.name
                # Prefer the leaf directory name unless it collides
                if skill_name in names_seen:
                    # Use parent dir as prefix to disambiguate
                    skill_name = f"{root.name}-{item.name}"
                if skill_name not in names_seen:
                    skills.append({
                        "name": skill_name,
                        "path": str(skill_file),
                        "source": source,
                    })
                    names_seen.add(skill_name)
            else:
                # Recurse one level deeper (kwp/<plugin>/<skill>/SKILL.md)
                self._discover_nested_skills(item, skills, source, depth + 1)

    def _is_skill_archived(self, name: str) -> bool:
        """Check whether a skill is archived."""
        meta = self.get_skill_metadata(name)
        if not meta:
            return False
        archived = meta.get("archived")
        if archived is True:
            return True
        if isinstance(archived, str) and archived.lower() == "true":
            return True
        return False

    def get_skill_path(self, name: str) -> Path | None:
        """Return the path to a skill's SKILL.md file."""
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill

        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill

        # Search nested built-in skills (e.g. kwp/<plugin>/<skill>/SKILL.md)
        if self.builtin_skills:
            for entry in self.builtin_skills.glob("**/" + name + "/SKILL.md"):
                return entry

        return None

    def load_skill(self, name: str) -> str | None:
        """
        Load a skill by name.

        Args:
            name: Skill name (directory name).

        Returns:
            Skill content or None if not found.
        """
        # Check workspace first
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")

        # Check built-in (flat)
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")

        # Check built-in (nested — kwp/<plugin>/<skill>/SKILL.md)
        if self.builtin_skills:
            for entry in self.builtin_skills.glob("**/" + name + "/SKILL.md"):
                return entry.read_text(encoding="utf-8")

        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        Load specific skills for inclusion in agent context.

        Args:
            skill_names: List of skill names to load.

        Returns:
            Formatted skills content.
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    def load_skill_by_path(self, path: str) -> str | None:
        """
        Load a skill's content from its indexed path.

        Nested built-in skills can get a synthesized display name
        (e.g. ``plugin-foo`` when ``foo`` collides) that has no matching
        directory, so callers holding a skill record should load by path.
        """
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            return None

    def load_skills_records_for_context(self, records: list[dict[str, str]]) -> str:
        """Load formatted skill bodies from list_skills records (by path)."""
        parts = []
        for rec in records:
            content = self.load_skill_by_path(rec["path"])
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {rec['name']}\n\n{content}")
        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(
        self,
        all_skills: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Build a summary of all skills (name, description, path, availability).

        This is used for progressive loading - the agent can read the full
        skill content using read_file when needed.

        Follows Anthropic's progressive-disclosure design:
        - Layer 1 (this summary): name + description + relative path
        - Layer 2 (on demand): full SKILL.md via read_file
        - Layer 3 (on demand): references/ siblings, scripts/, etc.

        Paths are emitted relative to the workspace when possible, so the
        agent can read them with relative paths. This matches the Claude
        Code / Cowork convention of `pdf/SKILL.md`-style locations.

        Args:
            all_skills: Optional pre-scanned skill list (list_skills output)
                to reuse instead of scanning the filesystem again. Callers
                that already hold a scan (e.g. for intent matching) pass it
                here to avoid a duplicate directory scan per turn (#613).

        Returns:
            XML-formatted skills summary.
        """
        if all_skills is None:
            all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""

        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        def relative_path(absolute: str) -> str:
            """Convert absolute SKILL.md path to a short relative path.

            Examples:
              C:/.../miqi/skills/pdf/SKILL.md          -> pdf/SKILL.md
              C:/.../miqi/skills/kwp/sales/call-prep/SKILL.md
                                                    -> kwp/sales/call-prep/SKILL.md
              <workspace>/skills/custom/SKILL.md       -> skills/custom/SKILL.md
            """
            p = Path(absolute)
            try:
                if self.builtin_skills:
                    rel = p.relative_to(self.builtin_skills)
                    if str(rel) != str(p.name):  # not the builtin root itself
                        return str(rel).replace("\\", "/")
                rel = p.relative_to(self.workspace)
                return str(rel).replace("\\", "/")
            except ValueError:
                return p.name

        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            rel_path = relative_path(s["path"])
            desc = escape_xml(self._get_skill_description(s["name"], s["path"]))
            skill_meta = self._get_skill_meta(s["name"], s["path"])
            available = self._check_requirements(skill_meta)

            lines.append(f'  <skill available="{str(available).lower()}">')
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{rel_path}</location>")

            # Surface references/ siblings so the agent knows there's a
            # third layer (Anthropic's progressive-disclosure level 3).
            skill_dir = Path(s["path"]).parent
            refs = sorted(p.name for p in skill_dir.glob("*.md")
                          if p.name.lower() != "skill.md")
            if refs:
                lines.append("    <references>" +
                             ", ".join(escape_xml(r) for r in refs) +
                             "</references>")

            # Show missing requirements for unavailable skills
            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")

            lines.append("  </skill>")
        lines.append("</skills>")

        return "\n".join(lines)

    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """Get a description of missing requirements."""
        missing = []
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        return ", ".join(missing)

    def _get_skill_description(self, name: str, path: str | None = None) -> str:
        """Get the description of a skill from its frontmatter."""
        if path is not None:
            meta = self.get_skill_metadata_by_path(path)
        else:
            meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name  # Fallback to skill name

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def _parse_skill_metadata(self, raw: str) -> dict:
        """Parse metadata JSON from frontmatter (miqi/assistant/openclaw keys)."""
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return {}
            return data.get("miqi", data.get("assistant", data.get("openclaw", {})))
        except (json.JSONDecodeError, TypeError):
            return {}

    def _check_requirements(self, skill_meta: dict) -> bool:
        """Check if skill requirements are met (bins, env vars)."""
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        return True

    def _get_skill_meta(self, name: str, path: str | None = None) -> dict:
        """Get normalized metadata for a skill (cached in frontmatter)."""
        if path is not None:
            meta = self.get_skill_metadata_by_path(path) or {}
        else:
            meta = self.get_skill_metadata(name) or {}
        return self._parse_skill_metadata(meta.get("metadata", ""))

    def get_always_skills(self) -> list[str]:
        """Get skills marked as always=true that meet requirements."""
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_skill_metadata(meta.get("metadata", ""))
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result

    def get_skill_metadata(self, name: str) -> dict | None:
        """
        Get metadata from a skill's frontmatter.

        Args:
            name: Skill name.

        Returns:
            Metadata dict or None.
        """
        if name in self._meta_cache:
            return self._meta_cache[name]
        meta = self._load_skill_metadata_uncached(name)
        self._meta_cache[name] = meta
        return meta

    def get_skill_metadata_by_path(self, path: str) -> dict | None:
        """
        Get metadata from a skill's frontmatter by indexed path.

        Nested built-ins can get a synthesized display name (``plugin-foo``)
        with no matching directory, so metadata must be read from the
        indexed path, not the display name.
        """
        cache_key = f"path:{path}"
        if cache_key in self._meta_cache:
            return self._meta_cache[cache_key]
        meta = self._load_skill_metadata_uncached(path, by_path=True)
        self._meta_cache[cache_key] = meta
        return meta

    def _load_skill_metadata_uncached(self, name: str, by_path: bool = False) -> dict | None:
        """Frontmatter parse, no cache lookup — used by get_skill_metadata."""
        if by_path:
            content = self.load_skill_by_path(name)
        else:
            content = self.load_skill(name)
        if not content:
            return None

        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                # Simple YAML parsing with basic type coercion
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        raw = value.strip().strip("\"'")
                        # Boolean coercion to Python bool
                        if raw.lower() in ("true", "yes"):
                            metadata[key.strip()] = True
                        elif raw.lower() in ("false", "no"):
                            metadata[key.strip()] = False
                        else:
                            metadata[key.strip()] = raw
                return metadata

        return None
