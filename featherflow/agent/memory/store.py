"""Memory system for persistent and short-term agent memory.

This module provides the main ``MemoryStore`` class which composes:
- :class:`~featherflow.agent.memory.snapshot.SnapshotStore` (long-term items)
- :class:`~featherflow.agent.memory.lessons.LessonStore` (self-improvement lessons)
- :class:`~featherflow.agent.memory.nlp.TextProcessor` (text utilities)
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from featherflow.agent.memory.lessons import LessonStore
from featherflow.agent.memory.nlp import TextProcessor
from featherflow.agent.memory.snapshot import SnapshotStore
from featherflow.utils.helpers import ensure_dir, timestamp, today_date


class MemoryStore:
    """
    Memory system for the agent.

    Supports:
    - Daily notes (memory/YYYY-MM-DD.md)
    - Legacy long-term notes (memory/MEMORY.md)
    - RAM-first long-term snapshot (memory/LTM_SNAPSHOT.json)
    - Session short-term working memory (in-memory only)
    - Self-improvement lessons
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

        self.flush_every_updates = max(1, flush_every_updates)
        self.flush_interval_seconds = max(1, flush_interval_seconds)
        self.short_term_turns = max(1, short_term_turns)
        self.pending_limit = max(1, pending_limit)
        self.self_improvement_enabled = self_improvement_enabled

        # Delegate stores
        self._snapshot_store = SnapshotStore(
            memory_dir=self.memory_dir,
            audit_file=self.memory_dir / "LTM_AUDIT.jsonl",
        )
        self._lesson_store = LessonStore(
            lessons_file=self.memory_dir / "LESSONS.jsonl",
            lessons_audit_file=self.memory_dir / "LESSONS_AUDIT.jsonl",
            enabled=self_improvement_enabled,
            max_lessons_in_prompt=max_lessons_in_prompt,
            min_lesson_confidence=min_lesson_confidence,
            max_lessons=max_lessons,
            lesson_confidence_decay_hours=lesson_confidence_decay_hours,
            feedback_max_message_chars=feedback_max_message_chars,
            feedback_require_prefix=feedback_require_prefix,
            promotion_enabled=promotion_enabled,
            promotion_min_users=promotion_min_users,
            promotion_triggers=promotion_triggers,
        )

        # Expose for backward compat
        self.snapshot_file = self._snapshot_store.snapshot_file
        self.audit_file = self._snapshot_store.audit_file
        self.lessons_file = self._lesson_store.lessons_file
        self.lessons_audit_file = self._lesson_store.lessons_audit_file
        self.max_lessons_in_prompt = self._lesson_store.max_lessons_in_prompt
        self.min_lesson_confidence = self._lesson_store.min_lesson_confidence
        self.max_lessons = self._lesson_store.max_lessons
        self.lesson_confidence_decay_hours = self._lesson_store.lesson_confidence_decay_hours
        self.feedback_max_message_chars = self._lesson_store.feedback_max_message_chars
        self.feedback_require_prefix = self._lesson_store.feedback_require_prefix
        self.promotion_enabled = self._lesson_store.promotion_enabled
        self.promotion_min_users = self._lesson_store.promotion_min_users
        self.promotion_triggers = self._lesson_store.promotion_triggers

        self._loaded = False
        self._short_term: dict[str, deque[dict[str, str]]] = {}
        self._pending: dict[str, deque[str]] = {}
        self._dirty_updates = 0
        self._last_flush_monotonic = time.monotonic()
        self._state_lock = threading.RLock()

    # ── Backward-compat properties ──

    @property
    def _lessons(self) -> list[dict[str, Any]]:
        """Proxy to lesson store lessons list (backward compat)."""
        self._load_once()
        return self._lesson_store.lessons

    @property
    def _items(self) -> list[dict[str, Any]]:
        """Proxy to snapshot store items list (backward compat)."""
        self._load_once()
        return self._snapshot_store.items

    # ── Backward-compatible class methods (delegate to TextProcessor) ──

    @staticmethod
    def _normalize_text(text: str) -> str:
        return TextProcessor.normalize_text(text)

    @staticmethod
    def _clean_text(text: str, max_len: int) -> str:
        return TextProcessor.clean_text(text, max_len)

    @staticmethod
    def _clean_text_with_tail(text: str, max_len: int, head_chars: int) -> str:
        return TextProcessor.clean_text_with_tail(text, max_len, head_chars)

    @classmethod
    def _tokenize(cls, text: str) -> set[str]:
        return TextProcessor.tokenize(text)

    @classmethod
    def _tokenize_terms(cls, text: str) -> list[str]:
        return TextProcessor.tokenize_terms(text)

    @classmethod
    def _normalize_token(cls, token: str) -> str:
        return TextProcessor.normalize_token(token)

    @staticmethod
    def _recency_bonus(iso_time: str) -> float:
        return TextProcessor.recency_bonus(iso_time)

    @staticmethod
    def _extract_path_hint(result: str) -> str:
        return TextProcessor.extract_path_hint(result)

    @staticmethod
    def _extract_param_name(result: str) -> str:
        return TextProcessor.extract_param_name(result)

    # ── Daily notes ──

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
        from datetime import datetime, timedelta

        memories = []
        today = datetime.now().date()
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                memories.append(content)
        return "\n\n---\n\n".join(memories)

    def list_memory_files(self) -> list[Path]:
        """List all memory files sorted by date (newest first)."""
        if not self.memory_dir.exists():
            return []
        files = list(self.memory_dir.glob("????-??-??.md"))
        return sorted(files, reverse=True)

    # ── Snapshot delegation ──

    def remember(
        self,
        text: str,
        session_key: str | None = None,
        source: str = "explicit_user",
        immediate: bool = False,
    ) -> bool:
        """Add or update a long-term memory item."""
        with self._state_lock:
            self._load_once()
            result = self._snapshot_store.remember(text, session_key, source)
            if result:
                self._dirty_updates += 1
                if immediate:
                    self.flush(force=True)
                else:
                    self.flush_if_needed()
            return result

    def compact(self, max_items: int = DEFAULT_MAX_LTM_ITEMS, auto_flush: bool = True) -> int:
        """Compact long-term snapshot."""
        with self._state_lock:
            self._load_once()
            removed = self._snapshot_store.compact(max_items)
            if removed > 0:
                self._dirty_updates += 1
                if auto_flush:
                    self.flush_if_needed()
            return removed

    def list_snapshot_items(
        self, session_key: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List snapshot items sorted by recency/hits."""
        with self._state_lock:
            self._load_once()
            return self._snapshot_store.list_items(session_key, limit)

    def delete_snapshot_item(self, item_id: str, immediate: bool = True) -> bool:
        """Delete a long-term snapshot item by id."""
        with self._state_lock:
            self._load_once()
            result = self._snapshot_store.delete_item(item_id)
            if result:
                self._dirty_updates += 1
                if immediate:
                    self.flush(force=True)
                else:
                    self.flush_if_needed()
            return result

    # ── Lesson delegation ──

    def learn_lesson(
        self,
        trigger: str,
        bad_action: str,
        better_action: str,
        session_key: str | None = None,
        actor_key: str | None = None,
        source: str = "unknown",
        scope: str = "session",
        confidence_delta: int = 1,
        immediate: bool = False,
    ) -> bool:
        """Add or update a self-improvement lesson."""
        with self._state_lock:
            self._load_once()
            result = self._lesson_store.learn(
                trigger, bad_action, better_action, session_key,
                actor_key, source, scope, confidence_delta,
            )
            if result:
                self._dirty_updates += 1
                if immediate:
                    self.flush(force=True)
                else:
                    self.flush_if_needed()
            return result

    def record_tool_feedback(self, session_key: str, tool_name: str, result: str) -> bool:
        """Learn lesson from a tool execution result."""
        with self._state_lock:
            self._load_once()
            updated = self._lesson_store.record_tool_feedback(session_key, tool_name, result)
            if updated:
                self._dirty_updates += 1
                self.flush_if_needed()
            return updated

    def record_user_feedback(
        self,
        session_key: str,
        user_message: str,
        previous_assistant: str | None = None,
        actor_key: str | None = None,
    ) -> bool:
        """Learn lesson from explicit user correction/feedback."""
        with self._state_lock:
            self._load_once()
            result = self._lesson_store.record_user_feedback(
                session_key, user_message, previous_assistant, actor_key
            )
            if result:
                self._dirty_updates += 1
                self.flush_if_needed()
            return result

    def get_lessons_for_context(
        self,
        session_key: str | None = None,
        current_message: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select top lessons for prompt context."""
        with self._state_lock:
            self._load_once()
            return self._lesson_store.get_lessons_for_context(session_key, current_message, limit)

    def compact_lessons(self, max_lessons: int | None = None, auto_flush: bool = True) -> int:
        """Compact self-improvement lessons."""
        with self._state_lock:
            self._load_once()
            removed = self._lesson_store.compact_lessons(max_lessons)
            if removed > 0:
                self._dirty_updates += 1
                if auto_flush:
                    self.flush_if_needed()
            return removed

    def reset_lessons(self) -> int:
        """Reset all lessons and return removed count."""
        with self._state_lock:
            self._load_once()
            removed = self._lesson_store.reset()
            if removed > 0:
                self._dirty_updates += 1
                self.flush(force=True)
            return removed

    def list_lessons(
        self,
        scope: str = "all",
        session_key: str | None = None,
        limit: int = 50,
        include_disabled: bool = False,
    ) -> list[dict[str, Any]]:
        """List lessons with filtering and ranking metadata."""
        with self._state_lock:
            self._load_once()
            return self._lesson_store.list_lessons(scope, session_key, limit, include_disabled)

    def set_lesson_enabled(self, lesson_id: str, enabled: bool, immediate: bool = True) -> bool:
        """Enable or disable a lesson by id."""
        with self._state_lock:
            self._load_once()
            result = self._lesson_store.set_enabled(lesson_id, enabled)
            if result:
                self._dirty_updates += 1
                if immediate:
                    self.flush(force=True)
                else:
                    self.flush_if_needed()
            return result

    def delete_lesson(self, lesson_id: str, immediate: bool = True) -> bool:
        """Delete a lesson by id."""
        with self._state_lock:
            self._load_once()
            result = self._lesson_store.delete(lesson_id)
            if result:
                self._dirty_updates += 1
                if immediate:
                    self.flush(force=True)
                else:
                    self.flush_if_needed()
            return result

    # ── Short-term memory & turn tracking ──

    def record_turn(
        self,
        session_key: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Update short-term memory and learn explicit long-term rules from the turn."""
        with self._state_lock:
            self._load_once()

            turns = self._short_term.setdefault(session_key, deque(maxlen=self.short_term_turns))
            turns.append(
                {
                    "user": TextProcessor.clean_text(user_message, max_len=320),
                    "assistant": TextProcessor.clean_text_with_tail(
                        assistant_message, max_len=800, head_chars=560,
                    ),
                }
            )

            pending_item = self._extract_pending_item(user_message)
            if pending_item:
                queue = self._pending.setdefault(session_key, deque(maxlen=self.pending_limit))
                queue.append(pending_item)

            if self._is_pending_resolved(user_message):
                queue = self._pending.get(session_key)
                if queue:
                    queue.popleft()

            explicit_memories = self._extract_explicit_memories(user_message)
            for fact in explicit_memories:
                self.remember(fact, session_key=session_key, source="explicit_user", immediate=True)

            self.flush_if_needed()

    # ── Memory context ──

    def get_memory_context(
        self, session_key: str | None = None, current_message: str | None = None
    ) -> str:
        """Get memory context for the agent."""
        with self._state_lock:
            self._load_once()
            parts: list[str] = []

            lessons = self.get_lessons_for_context(
                session_key=session_key,
                current_message=current_message,
                limit=self.max_lessons_in_prompt,
            )
            if lessons:
                lesson_lines = [
                    f"- When {lesson['trigger']}: {lesson['better_action']} "
                    f"(confidence={lesson.get('confidence', 1)})"
                    for lesson in lessons
                ]
                parts.append("## Lessons\n" + "\n".join(lesson_lines))

            snapshot_items = self._snapshot_store.select_items(
                session_key=session_key, limit=8, current_message=current_message,
            )
            if snapshot_items:
                lines = [f"- {item['text']}" for item in snapshot_items]
                parts.append("## Long-term Memory (Snapshot)\n" + "\n".join(lines))

            long_term = self.read_long_term()
            if long_term:
                if snapshot_items:
                    legacy = TextProcessor.clean_text(long_term, max_len=900)
                    parts.append("## Legacy Long-term Notes\n" + legacy)
                else:
                    # Hard cap to avoid token explosion when snapshot is empty.
                    _LT_MAX = 8000
                    if len(long_term) > _LT_MAX:
                        long_term = long_term[:_LT_MAX] + "\n... (truncated)"
                    parts.append("## Long-term Memory\n" + long_term)

            today = self.read_today()
            if today:
                # Today's notes are high-signal but can grow unbounded via heartbeat.
                _TODAY_MAX = 12000
                if len(today) > _TODAY_MAX:
                    today = today[:_TODAY_MAX] + "\n... (truncated)"
                parts.append("## Today's Notes\n" + today)

            if session_key:
                turns = self._short_term.get(session_key)
                if turns:
                    short_lines = []
                    for turn in list(turns)[-6:]:
                        user = turn.get("user", "")
                        assistant = turn.get("assistant", "")
                        short_lines.append(f"- User: {user}\n  Assistant: {assistant}")
                    parts.append("## Short-term Working Memory\n" + "\n".join(short_lines))

                pending = self._pending.get(session_key)
                if pending:
                    pending_lines = [f"- {item}" for item in list(pending)]
                    parts.append("## Pending Items\n" + "\n".join(pending_lines))

            return "\n\n".join(parts) if parts else ""

    # ── Status ──

    def get_status(self) -> dict[str, Any]:
        """Get in-memory status and snapshot statistics."""
        with self._state_lock:
            self._load_once()
            return {
                "snapshot_path": str(self.snapshot_file),
                "audit_path": str(self.audit_file),
                "ltm_items": len(self._snapshot_store.items),
                "short_term_sessions": len(self._short_term),
                "pending_sessions": len(self._pending),
                "dirty_updates": self._dirty_updates,
                "flush_every_updates": self.flush_every_updates,
                "flush_interval_seconds": self.flush_interval_seconds,
                "last_snapshot_at": self._snapshot_store.updated_at,
                "snapshot_exists": self.snapshot_file.exists(),
                "lessons_file": str(self.lessons_file),
                "lessons_audit_file": str(self.lessons_audit_file),
                "self_improvement_enabled": self.self_improvement_enabled,
                "lessons_count": len(self._lesson_store.lessons),
                "max_lessons_in_prompt": self.max_lessons_in_prompt,
                "min_lesson_confidence": self.min_lesson_confidence,
                "max_lessons": self.max_lessons,
                "lesson_confidence_decay_hours": self.lesson_confidence_decay_hours,
                "feedback_max_message_chars": self.feedback_max_message_chars,
                "feedback_require_prefix": self.feedback_require_prefix,
                "promotion_enabled": self.promotion_enabled,
                "promotion_min_users": self.promotion_min_users,
                "promotion_triggers": sorted(self.promotion_triggers),
            }

    # ── Flush ──

    def flush_if_needed(self, force: bool = False) -> bool:
        """Flush snapshot/audit to disk when thresholds are reached."""
        with self._state_lock:
            self._load_once()
            has_pending = (
                self._dirty_updates > 0
                or self._snapshot_store.dirty
                or self._lesson_store.dirty
                or self._snapshot_store.has_pending_audits
                or self._lesson_store.has_pending_audits
            )

            if not has_pending:
                return False

            if force:
                self._flush_to_disk()
                return True

            elapsed = time.monotonic() - self._last_flush_monotonic
            should_flush = (
                self._dirty_updates >= self.flush_every_updates
                or elapsed >= self.flush_interval_seconds
            )
            if not should_flush:
                return False

            self._flush_to_disk()
            return True

    def flush(self, force: bool = False) -> bool:
        """Flush memory state to disk."""
        return self.flush_if_needed(force=force)

    # ── Internal ──

    def _load_once(self) -> None:
        """Load snapshot from disk once (RAM-first)."""
        with self._state_lock:
            if self._loaded:
                return
            self._snapshot_store.load()
            self._lesson_store.load()
            self._loaded = True

    def _flush_to_disk(self) -> None:
        """Persist all state to disk."""
        with self._state_lock:
            self._snapshot_store.flush()
            self._lesson_store.flush()
            self._dirty_updates = 0
            self._last_flush_monotonic = time.monotonic()

    def _select_snapshot_items(
        self, session_key: str | None, limit: int, current_message: str | None = None,
    ) -> list[dict[str, Any]]:
        """Select long-term items for prompt context (backward compat)."""
        return self._snapshot_store.select_items(session_key, limit, current_message)

    # ── Text extraction helpers ──

    @staticmethod
    def _extract_explicit_memories(message: str) -> list[str]:
        """Extract explicit long-term memory intents from user messages."""
        text = message.strip()
        if not text:
            return []

        candidates: list[str] = []
        lower = text.lower()

        cn_match = re.search(r"(?:请)?记住[:：\s]*(.+)$", text)
        if cn_match:
            candidates.append(cn_match.group(1))

        en_match = re.search(r"(?:please\s+)?remember(?:\s+that)?[:\s]+(.+)$", lower)
        if en_match:
            candidates.append(text[en_match.start(1):])

        if not candidates and any(token in text for token in ("以后都", "以后请", "长期", "默认")):
            candidates.append(text)
        if not candidates and any(token in lower for token in ("from now on", "always", "default")):
            candidates.append(text)

        cleaned = [TextProcessor.clean_text(c, max_len=280) for c in candidates]
        return [c for c in cleaned if c]

    @staticmethod
    def _extract_pending_item(message: str) -> str | None:
        """Extract pending item hints from user messages."""
        text = message.strip()
        if not text:
            return None

        lower = text.lower()
        markers = ("todo", "to-do", "待办", "请提醒", "remember to", "别忘了")
        if any(marker in lower for marker in markers) or any(marker in text for marker in markers):
            return TextProcessor.clean_text(text, max_len=180)
        return None

    @staticmethod
    def _is_pending_resolved(message: str) -> bool:
        """Check if user indicates pending items are resolved/canceled."""
        lower = message.lower()
        markers = ("done", "resolved", "cancel", "不用了", "已完成", "完成了", "取消")
        return any(marker in lower for marker in markers) or any(
            marker in message for marker in markers
        )

    @staticmethod
    def _is_tool_error(result: str) -> bool:
        """Check whether tool result string indicates an error."""
        return result.strip().lower().startswith("error:")

    def _suggest_tool_better_action(self, tool_name: str, result: str) -> str:
        """Suggest a lightweight fix action for common tool failures."""
        return self._lesson_store._suggest_tool_better_action(tool_name, result)

    def _lesson_key(
        self, trigger: str, better_action: str, scope: str, session_key: str | None
    ) -> str:
        """Build a stable dedup key for lessons."""
        return self._lesson_store._lesson_key(trigger, better_action, scope, session_key)

    def _has_feedback_prefix(self, user_message: str) -> bool:
        return self._lesson_store._has_feedback_prefix(user_message)

    def _extract_feedback_signal(self, user_message: str) -> tuple[str, str] | None:
        return self._lesson_store._extract_feedback_signal(user_message)

    def _summarize_bad_action(self, previous_assistant: str) -> str:
        return self._lesson_store._summarize_bad_action(previous_assistant)

    @staticmethod
    def _user_key_from_session(session_key: str | None) -> str:
        return LessonStore._user_key_from_session(session_key)
