"""Memory system for persistent and short-term agent memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.utils.helpers import ensure_dir, timestamp, today_date

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session


_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A paragraph (2-5 sentences) summarizing key events/decisions/topics. "
                        "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "Full updated long-term memory as markdown. Include all existing "
                        "facts plus new ones. Return unchanged if nothing new.",
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]


class MemoryStore:
    """
    Memory system for the agent.

    Supports:
    - Daily notes (memory/YYYY-MM-DD.md)
    - Legacy long-term notes (memory/MEMORY.md)
    - RAM-first long-term snapshot (memory/LTM_SNAPSHOT.json)
    - Session short-term working memory (in-memory only)
    """

    DEFAULT_FLUSH_EVERY_UPDATES = 8
    DEFAULT_FLUSH_INTERVAL_SECONDS = 120
    DEFAULT_SHORT_TERM_TURNS = 12
    DEFAULT_PENDING_LIMIT = 20
    DEFAULT_MAX_LTM_ITEMS = 300
    DEFAULT_COMPACT_TRIGGER_RATIO = 1.1
    DEFAULT_MAX_LESSONS = 200
    DEFAULT_MAX_LESSONS_IN_PROMPT = 5
    DEFAULT_MIN_LESSON_CONFIDENCE = 1
    DEFAULT_LESSON_CONFIDENCE_DECAY_HOURS = 168
    DEFAULT_FEEDBACK_MAX_MESSAGE_CHARS = 220
    DEFAULT_FEEDBACK_REQUIRE_PREFIX = True
    DEFAULT_PROMOTION_ENABLED = True
    DEFAULT_PROMOTION_MIN_USERS = 3
    DEFAULT_PROMOTION_TRIGGERS = ("response:length", "response:language")

    EN_STOPWORDS = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "with",
        "this",
        "that",
        "you",
        "your",
        "are",
        "is",
        "to",
        "of",
        "in",
        "on",
        "it",
        "we",
        "our",
        "can",
        "please",
        "from",
        "now",
        "then",
        "still",
        "first",
        "just",
    }
    ZH_STOPWORDS = {
        "这个",
        "那个",
        "一下",
        "然后",
        "就是",
        "我们",
        "你们",
        "还有",
        "以及",
        "是否",
        "可以",
        "需要",
        "已经",
        "现在",
    }
    TOKEN_SYNONYMS = {
        "paths": "path",
        "路径": "path",
        "repo": "repo",
        "repository": "repo",
        "仓库": "repo",
        "project": "project",
        "projects": "project",
        "项目": "project",
        "config": "config",
        "configuration": "config",
        "配置": "config",
        "database": "database",
        "databases": "database",
        "数据库": "database",
        "memory": "memory",
        "memories": "memory",
        "记忆": "memory",
        "lesson": "lesson",
        "lessons": "lesson",
        "教训": "lesson",
    }
    TOKEN_SUBSTRING_SYNONYMS = {
        "路径": "path",
        "仓库": "repo",
        "项目": "project",
        "配置": "config",
        "数据库": "database",
        "记忆": "memory",
        "教训": "lesson",
    }

    def __init__(
        self,
        workspace: Path,
        flush_every_updates: int = DEFAULT_FLUSH_EVERY_UPDATES,
        flush_interval_seconds: int = DEFAULT_FLUSH_INTERVAL_SECONDS,
        short_term_turns: int = DEFAULT_SHORT_TERM_TURNS,
        pending_limit: int = DEFAULT_PENDING_LIMIT,
        self_improvement_enabled: bool = True,
        max_lessons_in_prompt: int = DEFAULT_MAX_LESSONS_IN_PROMPT,
        min_lesson_confidence: int = DEFAULT_MIN_LESSON_CONFIDENCE,
        max_lessons: int = DEFAULT_MAX_LESSONS,
        lesson_confidence_decay_hours: int = DEFAULT_LESSON_CONFIDENCE_DECAY_HOURS,
        feedback_max_message_chars: int = DEFAULT_FEEDBACK_MAX_MESSAGE_CHARS,
        feedback_require_prefix: bool = DEFAULT_FEEDBACK_REQUIRE_PREFIX,
        promotion_enabled: bool = DEFAULT_PROMOTION_ENABLED,
        promotion_min_users: int = DEFAULT_PROMOTION_MIN_USERS,
        promotion_triggers: list[str] | tuple[str, ...] | None = None,
    ):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.snapshot_file = self.memory_dir / "LTM_SNAPSHOT.json"
        self.audit_file = self.memory_dir / "LTM_AUDIT.jsonl"
        self.lessons_file = self.memory_dir / "LESSONS.jsonl"
        self.lessons_audit_file = self.memory_dir / "LESSONS_AUDIT.jsonl"

        self.flush_every_updates = max(1, flush_every_updates)
        self.flush_interval_seconds = max(1, flush_interval_seconds)
        self.short_term_turns = max(1, short_term_turns)
        self.pending_limit = max(1, pending_limit)
        self.self_improvement_enabled = self_improvement_enabled
        self.max_lessons_in_prompt = max(1, max_lessons_in_prompt)
        self.min_lesson_confidence = min_lesson_confidence
        self.max_lessons = max(1, max_lessons)
        self.lesson_confidence_decay_hours = max(1, lesson_confidence_decay_hours)
        self.feedback_max_message_chars = max(1, feedback_max_message_chars)
        self.feedback_require_prefix = feedback_require_prefix
        self.promotion_enabled = promotion_enabled
        self.promotion_min_users = max(2, promotion_min_users)
        configured_triggers = promotion_triggers or list(self.DEFAULT_PROMOTION_TRIGGERS)
        normalized_triggers = [
            self._clean_text(str(trigger), max_len=120) for trigger in configured_triggers
        ]
        self.promotion_triggers = {
            trigger for trigger in normalized_triggers if trigger and ":" in trigger
        }

        self._loaded = False
        self._snapshot: dict[str, Any] = {"version": 1, "updated_at": timestamp(), "items": []}
        self._short_term: dict[str, deque[dict[str, str]]] = {}
        self._pending: dict[str, deque[str]] = {}
        self._lessons: list[dict[str, Any]] = []
        self._dirty_updates = 0
        self._last_flush_monotonic = time.monotonic()
        self._audit_buffer: list[dict[str, Any]] = []
        self._lessons_audit_buffer: list[dict[str, Any]] = []
        self._snapshot_dirty = False
        self._lessons_dirty = False
        self._state_lock = threading.RLock()

    def get_today_file(self) -> Path:
        """Get path to today's memory file."""
        return self.memory_dir / f"{today_date()}.md"

    def read_today(self) -> str:
        """Read today's memory notes."""
        today_file = self.get_today_file()
        if today_file.exists():
            return today_file.read_text(encoding="utf-8")
        return ""

    def append_today(self, content: str) -> None:
        """Append content to today's memory notes."""
        today_file = self.get_today_file()

        if today_file.exists():
            existing = today_file.read_text(encoding="utf-8")
            content = existing + "\n" + content
        else:
            header = f"# {today_date()}\n\n"
            content = header + content

        today_file.write_text(content, encoding="utf-8")

    def read_long_term(self) -> str:
        """Read legacy long-term memory (MEMORY.md)."""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        """Write to legacy long-term memory (MEMORY.md)."""
        self.memory_file.write_text(content, encoding="utf-8")

    def get_recent_memories(self, days: int = 7) -> str:
        """Get memories from the last N days."""
        from datetime import timedelta

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    async def consolidate(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
        *,
        archive_all: bool = False,
        memory_window: int = 50,
    ) -> bool:
        """Consolidate old messages into MEMORY.md + HISTORY.md via LLM tool call.

        Returns True on success (including no-op), False on failure.
        """
        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info("Memory consolidation (archive_all): {} messages", len(session.messages))
        else:
            keep_count = memory_window // 2
            if len(session.messages) <= keep_count:
                return True
            if len(session.messages) - session.last_consolidated <= 0:
                return True
            old_messages = session.messages[session.last_consolidated:-keep_count]
            if not old_messages:
                return True
            logger.info("Memory consolidation: {} to consolidate, {} keep", len(old_messages), keep_count)

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}")

        current_memory = self.read_long_term()
        prompt = f"""Process this conversation and call the save_memory tool with your consolidation.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{chr(10).join(lines)}"""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a memory consolidation agent. Call the save_memory tool with your consolidation of the conversation."},
                    {"role": "user", "content": prompt},
                ],
                tools=_SAVE_MEMORY_TOOL,
                model=model,
            )

            if not response.has_tool_calls:
                logger.warning("Memory consolidation: LLM did not call save_memory, skipping")
                return False

            args = response.tool_calls[0].arguments
            if entry := args.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                self.append_history(entry)
            if update := args.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    self.write_long_term(update)

            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            logger.info("Memory consolidation done: {} messages, last_consolidated={}", len(session.messages), session.last_consolidated)
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return False
