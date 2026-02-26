"""Self-improvement lesson system: learn, promote, and manage lessons."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from featherflow.agent.memory.nlp import TextProcessor
from featherflow.utils.helpers import timestamp


class LessonStore:
    """Manages self-improvement lessons (LESSONS.jsonl)."""

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
        lessons_file: Path,
        lessons_audit_file: Path,
        *,
        enabled: bool = True,
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
        self.lessons_file = lessons_file
        self.lessons_audit_file = lessons_audit_file
        self.enabled = enabled
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
            TextProcessor.clean_text(str(trigger), max_len=120) for trigger in configured_triggers
        ]
        self.promotion_triggers = {
            trigger for trigger in normalized_triggers if trigger and ":" in trigger
        }

        self._lessons: list[dict[str, Any]] = []
        self._dirty = False
        self._audit_buffer: list[dict[str, Any]] = []

    @property
    def lessons(self) -> list[dict[str, Any]]:
        return self._lessons

    @property
    def dirty(self) -> bool:
        return self._dirty

    @dirty.setter
    def dirty(self, value: bool) -> None:
        self._dirty = value

    @property
    def has_pending_audits(self) -> bool:
        return bool(self._audit_buffer)

    def load(self) -> None:
        """Load lessons from LESSONS.jsonl."""
        if not self.lessons_file.exists():
            return

        lessons: list[dict[str, Any]] = []
        try:
            with open(self.lessons_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        continue
                    trigger = TextProcessor.clean_text(str(data.get("trigger", "")), max_len=120)
                    better_action = TextProcessor.clean_text(
                        str(data.get("better_action", "")), max_len=260
                    )
                    if not trigger or not better_action:
                        continue
                    scope = "session" if data.get("scope") == "session" else "global"
                    session_key = str(data.get("session_key", "")) if scope == "session" else ""
                    key = self._lesson_key(trigger, better_action, scope, session_key)
                    lessons.append(
                        {
                            "id": str(data.get("id", f"lesson_{len(lessons) + 1}")),
                            "key": key,
                            "trigger": trigger,
                            "bad_action": TextProcessor.clean_text(
                                str(data.get("bad_action", "")), max_len=260
                            ),
                            "better_action": better_action,
                            "scope": scope,
                            "session_key": session_key,
                            "actor_key": str(data.get("actor_key", "")),
                            "source": str(data.get("source", "unknown")),
                            "confidence": int(data.get("confidence", 1)),
                            "hits": int(data.get("hits", 1)),
                            "enabled": bool(data.get("enabled", True)),
                            "created_at": str(data.get("created_at", timestamp())),
                            "updated_at": str(data.get("updated_at", timestamp())),
                            "last_applied_at": str(data.get("last_applied_at", "")),
                            "promoted_global_key": str(data.get("promoted_global_key", "")),
                        }
                    )
        except Exception:
            self._lessons = []
            return
        self._lessons = lessons

    def flush(self) -> None:
        """Persist lessons and audit buffer to disk."""
        if self._dirty:
            tmp = self.lessons_file.with_suffix(".jsonl.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for lesson in self._lessons:
                    f.write(json.dumps(lesson, ensure_ascii=False) + "\n")
            tmp.replace(self.lessons_file)

        if self._audit_buffer:
            with open(self.lessons_audit_file, "a", encoding="utf-8") as f:
                for event in self._audit_buffer:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._audit_buffer = []

        self._dirty = False

    def learn(
        self,
        trigger: str,
        bad_action: str,
        better_action: str,
        session_key: str | None = None,
        actor_key: str | None = None,
        source: str = "unknown",
        scope: str = "session",
        confidence_delta: int = 1,
    ) -> bool:
        """Add or update a self-improvement lesson. Returns True if added/updated."""
        if not self.enabled:
            return False

        trigger = TextProcessor.clean_text(trigger, max_len=120)
        bad_action = TextProcessor.clean_text_with_tail(bad_action, max_len=260, head_chars=180)
        better_action = TextProcessor.clean_text(better_action, max_len=260)
        if not trigger or not better_action:
            return False

        now = timestamp()
        scope = "session" if scope == "session" else "global"
        lesson_key = self._lesson_key(trigger, better_action, scope, session_key)

        existing = None
        for lesson in self._lessons:
            if lesson.get("key") == lesson_key:
                existing = lesson
                break

        delta = max(1, confidence_delta)
        if existing:
            existing["updated_at"] = now
            existing["bad_action"] = bad_action or existing.get("bad_action", "")
            existing["better_action"] = better_action
            existing["hits"] = int(existing.get("hits", 0)) + 1
            existing["confidence"] = min(10, int(existing.get("confidence", 1)) + delta)
            if actor_key and scope == "session":
                existing["actor_key"] = actor_key
            self._audit_buffer.append(
                {
                    "type": "lesson_update",
                    "at": now,
                    "id": existing.get("id", ""),
                    "source": source,
                    "confidence": existing["confidence"],
                }
            )
        else:
            lesson_id = f"lesson_{int(time.time() * 1000)}_{len(self._lessons) + 1}"
            self._lessons.append(
                {
                    "id": lesson_id,
                    "key": lesson_key,
                    "trigger": trigger,
                    "bad_action": bad_action,
                    "better_action": better_action,
                    "scope": scope,
                    "session_key": session_key if scope == "session" else "",
                    "actor_key": actor_key if scope == "session" and actor_key else "",
                    "source": source,
                    "confidence": max(self.min_lesson_confidence, delta),
                    "hits": 1,
                    "enabled": True,
                    "created_at": now,
                    "updated_at": now,
                    "last_applied_at": "",
                    "promoted_global_key": "",
                }
            )
            self._audit_buffer.append(
                {
                    "type": "lesson_add",
                    "at": now,
                    "id": lesson_id,
                    "source": source,
                    "trigger": trigger,
                }
            )

        if scope == "session":
            self._maybe_promote_session_lesson(
                trigger=trigger, better_action=better_action, source=source
            )
        self._dirty = True
        self.compact_lessons(max_lessons=self.max_lessons)
        return True

    def record_tool_feedback(self, session_key: str, tool_name: str, result: str) -> bool:
        """Learn lesson from a tool execution result."""
        if not self.enabled:
            return False

        if self._is_tool_error(result):
            better_action = self._suggest_tool_better_action(tool_name, result)
            return self.learn(
                trigger=f"tool:{tool_name}:error",
                bad_action=result,
                better_action=better_action,
                session_key=session_key,
                source="tool_feedback",
                scope="session",
                confidence_delta=1,
            )

        now = timestamp()
        updated = False
        for lesson in self._lessons:
            if (
                lesson.get("enabled", True)
                and lesson.get("scope") == "session"
                and lesson.get("session_key") == session_key
                and lesson.get("trigger") == f"tool:{tool_name}:error"
            ):
                lesson["confidence"] = min(10, int(lesson.get("confidence", 1)) + 1)
                lesson["updated_at"] = now
                lesson["hits"] = int(lesson.get("hits", 0)) + 1
                lesson["last_applied_at"] = now
                updated = True
                self._audit_buffer.append(
                    {
                        "type": "lesson_reinforced",
                        "at": now,
                        "id": lesson.get("id", ""),
                        "source": "tool_success",
                    }
                )
                break

        if updated:
            self._dirty = True
        return updated

    def record_user_feedback(
        self,
        session_key: str,
        user_message: str,
        previous_assistant: str | None = None,
        actor_key: str | None = None,
    ) -> bool:
        """Learn lesson from explicit user correction/feedback."""
        if not self.enabled:
            return False

        if not previous_assistant or not previous_assistant.strip():
            return False

        text = user_message.strip()
        if not text:
            return False

        if len(text) > self.feedback_max_message_chars:
            return False

        if self.feedback_require_prefix and not self._has_feedback_prefix(text):
            return False

        feedback = self._extract_feedback_signal(text)
        if not feedback:
            return False

        trigger, better_action = feedback
        bad_action = self._summarize_bad_action(previous_assistant)
        return self.learn(
            trigger=trigger,
            bad_action=bad_action,
            better_action=better_action,
            session_key=session_key,
            actor_key=actor_key or self._user_key_from_session(session_key),
            source="user_feedback",
            scope="session",
            confidence_delta=2,
        )

    def get_lessons_for_context(
        self,
        session_key: str | None = None,
        current_message: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select top lessons for prompt context."""
        if not self.enabled:
            return []

        max_items = max(1, limit or self.max_lessons_in_prompt)
        lessons = []
        for lesson in self._lessons:
            if not lesson.get("enabled", True):
                continue
            raw_confidence = int(lesson.get("confidence", 0))
            if raw_confidence < self.min_lesson_confidence:
                continue
            if self._effective_lesson_confidence(lesson) <= 0:
                continue
            scope = lesson.get("scope", "session")
            lesson_session = lesson.get("session_key", "")
            if scope == "session" and session_key and lesson_session != session_key:
                continue
            if scope == "session" and not session_key:
                continue
            lessons.append(lesson)

        if not lessons:
            return []

        query_tokens = TextProcessor.tokenize(current_message or "")

        def _score(item: dict[str, Any]) -> tuple[float, float, int, str]:
            text = " ".join([
                str(item.get("trigger", "")),
                str(item.get("bad_action", "")),
                str(item.get("better_action", "")),
            ])
            lesson_tokens = TextProcessor.tokenize(text)
            overlap = len(query_tokens & lesson_tokens) if query_tokens else 0
            overlap_score = float(overlap) if overlap > 0 else 0.0
            recency = str(item.get("updated_at", ""))
            recency_val = TextProcessor.recency_bonus(recency)
            effective_confidence = self._effective_lesson_confidence(item)
            return (
                overlap_score + recency_val,
                effective_confidence,
                int(item.get("hits", 0)),
                recency,
            )

        lessons.sort(key=_score, reverse=True)
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for lesson in lessons:
            signature = (
                TextProcessor.normalize_text(str(lesson.get("trigger", ""))),
                TextProcessor.normalize_text(str(lesson.get("better_action", ""))),
            )
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(lesson)
            if len(deduped) >= max_items:
                break
        return deduped

    def compact_lessons(self, max_lessons: int | None = None) -> int:
        """Compact lessons by deduplicating and capping size. Returns removed count."""
        if not self.enabled:
            return 0

        max_keep = max(1, max_lessons or self.max_lessons)
        original_count = len(self._lessons)
        if original_count == 0:
            return 0

        dedup: dict[str, dict[str, Any]] = {}
        sorted_lessons = sorted(
            self._lessons,
            key=lambda x: (
                int(x.get("confidence", 0)),
                int(x.get("hits", 0)),
                x.get("updated_at", ""),
            ),
            reverse=True,
        )
        for lesson in sorted_lessons:
            if not lesson.get("enabled", True):
                continue
            if int(lesson.get("confidence", 0)) < self.min_lesson_confidence:
                continue
            key = str(lesson.get("key", ""))
            if key and key not in dedup:
                dedup[key] = lesson

        compacted = list(dedup.values())[:max_keep]
        removed = original_count - len(compacted)
        if removed <= 0:
            return 0

        self._lessons = compacted
        self._dirty = True
        self._audit_buffer.append(
            {"type": "lesson_compact", "at": timestamp(), "removed": removed, "kept": len(compacted)}
        )
        return removed

    def reset(self) -> int:
        """Reset all lessons and return removed count."""
        removed = len(self._lessons)
        if removed == 0:
            return 0

        self._lessons = []
        self._dirty = True
        self._audit_buffer.append({"type": "lesson_reset", "at": timestamp(), "removed": removed})
        return removed

    def list_lessons(
        self,
        scope: str = "all",
        session_key: str | None = None,
        limit: int = 50,
        include_disabled: bool = False,
    ) -> list[dict[str, Any]]:
        """List lessons with filtering and ranking metadata."""
        normalized_scope = scope if scope in {"session", "global", "all"} else "all"
        selected: list[dict[str, Any]] = []
        for lesson in self._lessons:
            if normalized_scope != "all" and lesson.get("scope") != normalized_scope:
                continue
            if session_key and lesson.get("session_key") != session_key:
                continue
            if not include_disabled and not lesson.get("enabled", True):
                continue
            copied = dict(lesson)
            copied["effective_confidence"] = round(self._effective_lesson_confidence(lesson), 3)
            selected.append(copied)
        selected.sort(
            key=lambda x: (
                float(x.get("effective_confidence", 0.0)),
                int(x.get("hits", 0)),
                str(x.get("updated_at", "")),
            ),
            reverse=True,
        )
        return selected[: max(1, limit)]

    def set_enabled(self, lesson_id: str, enabled: bool) -> bool:
        """Enable or disable a lesson by id."""
        normalized_id = lesson_id.strip()
        if not normalized_id:
            return False
        now = timestamp()
        for lesson in self._lessons:
            if str(lesson.get("id", "")) != normalized_id:
                continue
            lesson["enabled"] = bool(enabled)
            lesson["updated_at"] = now
            self._dirty = True
            self._audit_buffer.append(
                {
                    "type": "lesson_enable" if enabled else "lesson_disable",
                    "at": now,
                    "id": normalized_id,
                }
            )
            return True
        return False

    def delete(self, lesson_id: str) -> bool:
        """Delete a lesson by id."""
        normalized_id = lesson_id.strip()
        if not normalized_id:
            return False
        original_count = len(self._lessons)
        self._lessons = [
            lesson for lesson in self._lessons
            if str(lesson.get("id", "")) != normalized_id
        ]
        if len(self._lessons) == original_count:
            return False
        now = timestamp()
        self._dirty = True
        self._audit_buffer.append({"type": "lesson_delete", "at": now, "id": normalized_id})
        return True

    # ── Internal helpers ──

    def _lesson_key(
        self, trigger: str, better_action: str, scope: str, session_key: str | None
    ) -> str:
        """Build a stable dedup key for lessons."""
        normalized_scope = "session" if scope == "session" else "global"
        normalized_session = session_key or "" if normalized_scope == "session" else ""
        return "|".join([
            TextProcessor.normalize_text(trigger),
            TextProcessor.normalize_text(better_action),
            normalized_scope,
            normalized_session,
        ])

    def _effective_lesson_confidence(self, item: dict[str, Any]) -> float:
        """Apply time decay to lesson confidence for ranking/filtering."""
        raw = float(item.get("confidence", 0))
        anchor = str(item.get("last_applied_at") or item.get("updated_at") or "")
        if not anchor:
            return raw
        try:
            dt = datetime.fromisoformat(anchor)
            age_hours = max(0.0, (datetime.now() - dt).total_seconds() / 3600)
            decay = age_hours / float(self.lesson_confidence_decay_hours)
            return max(0.0, raw - decay)
        except Exception:
            return raw

    def _suggest_tool_better_action(self, tool_name: str, result: str) -> str:
        """Suggest a lightweight fix action for common tool failures."""
        lower = result.lower()
        param = TextProcessor.extract_param_name(result)
        path = TextProcessor.extract_path_hint(result)
        if "invalid parameters" in lower:
            if param:
                return (
                    f"Fix `{param}` in `{tool_name}` args, then validate the full argument "
                    "schema before retrying."
                )
            return f"Validate `{tool_name}` arguments against its schema before calling."
        if "not found" in lower:
            if path:
                return f"Check that `{path}` exists and is readable before calling `{tool_name}`."
            return f"Check path/resource existence before calling `{tool_name}`."
        if "permission" in lower or "outside allowed directory" in lower:
            if path:
                return (
                    f"Ensure `{path}` is inside allowed workspace and has permissions before "
                    f"`{tool_name}`."
                )
            return f"Check permissions/workspace boundaries before `{tool_name}`."
        if "timeout" in lower:
            return f"Use smaller scope or lighter parameters when calling `{tool_name}`."
        return f"Inspect `{tool_name}` result and adjust arguments before retrying once."

    @staticmethod
    def _is_tool_error(result: str) -> bool:
        """Check whether tool result string indicates an error."""
        return result.strip().lower().startswith("error:")

    def _has_feedback_prefix(self, user_message: str) -> bool:
        """Require correction cues to appear at the beginning of the message."""
        text = user_message.strip()
        if not text:
            return False
        lower = text.lower()
        prefixes = (
            "不对", "不是这个意思", "你刚才", "你上一个", "别这样", "不要这样",
            "wrong", "incorrect", "not what i meant", "too verbose", "too long",
        )
        return any(lower.startswith(prefix) for prefix in prefixes) or any(
            text.startswith(prefix) for prefix in prefixes
        )

    @staticmethod
    def _extract_feedback_signal(user_message: str) -> tuple[str, str] | None:
        """Extract user correction into (trigger, better_action)."""
        text = user_message.strip()
        if not text:
            return None

        lower = text.lower()
        correction_markers = (
            "不对", "不是这个意思", "别这样", "不要这样", "太啰嗦", "太长",
            "wrong", "incorrect", "not what i meant", "too verbose", "too long",
        )
        if not any(marker in lower for marker in correction_markers) and not any(
            marker in text for marker in correction_markers
        ):
            return None

        if any(token in text for token in ("中文", "英文", "英语")) or any(
            token in lower for token in ("chinese", "english", "language")
        ):
            trigger = "response:language"
        elif any(token in text for token in ("简短", "简洁", "太长", "太啰嗦")) or any(
            token in lower for token in ("concise", "shorter", "too verbose", "too long")
        ):
            trigger = "response:length"
        elif any(token in text for token in ("错误", "不对", "事实")) or any(
            token in lower for token in ("wrong", "incorrect", "factual")
        ):
            trigger = "response:accuracy"
        else:
            trigger = "response:alignment"

        return trigger, TextProcessor.clean_text(text, max_len=240)

    @staticmethod
    def _summarize_bad_action(previous_assistant: str) -> str:
        """Summarize problematic assistant output into a concise lesson input."""
        cleaned = re.sub(r"\s+", " ", previous_assistant.strip())
        if not cleaned:
            return "(No previous assistant content available.)"
        sentences = re.split(r"(?<=[.!?。！？])\s+", cleaned)
        summary = " ".join(sentences[:2]).strip()
        if not summary:
            summary = cleaned
        return TextProcessor.clean_text_with_tail(summary, max_len=260, head_chars=180)

    @staticmethod
    def _user_key_from_session(session_key: str | None) -> str:
        """Build a stable lightweight user key from a session key."""
        if not session_key:
            return ""
        text = session_key.strip()
        if not text:
            return ""
        if ":" in text:
            return text.split(":", 1)[1].strip()
        return text

    def _maybe_promote_session_lesson(self, trigger: str, better_action: str, source: str) -> None:
        """Promote repeated session lessons to a global lesson with safety guards."""
        if not self.promotion_enabled:
            return
        if source != "user_feedback":
            return
        if trigger not in self.promotion_triggers:
            return

        normalized_action = TextProcessor.normalize_text(better_action)
        if not normalized_action:
            return

        supporting_lessons: list[dict[str, Any]] = []
        actor_keys: set[str] = set()
        for lesson in self._lessons:
            if lesson.get("scope") != "session":
                continue
            if lesson.get("source") != "user_feedback":
                continue
            if lesson.get("trigger") != trigger:
                continue
            if TextProcessor.normalize_text(str(lesson.get("better_action", ""))) != normalized_action:
                continue
            actor_key = str(lesson.get("actor_key", "")).strip() or self._user_key_from_session(
                str(lesson.get("session_key", ""))
            )
            if not actor_key:
                continue
            actor_keys.add(actor_key)
            supporting_lessons.append(lesson)

        if len(actor_keys) < self.promotion_min_users:
            return

        now = timestamp()
        global_key = self._lesson_key(trigger, better_action, "global", None)
        existing_global = next(
            (
                lesson for lesson in self._lessons
                if lesson.get("scope") == "global" and lesson.get("key") == global_key
            ),
            None,
        )
        support_hits = sum(int(lesson.get("hits", 1)) for lesson in supporting_lessons)

        if existing_global:
            existing_global["updated_at"] = now
            existing_global["enabled"] = True
            existing_global["hits"] = max(int(existing_global.get("hits", 0)), support_hits)
            existing_global["confidence"] = min(
                10,
                max(int(existing_global.get("confidence", self.min_lesson_confidence)), len(actor_keys) + 1),
            )
            promoted_id = str(existing_global.get("id", ""))
        else:
            promoted_id = f"lesson_global_{int(time.time() * 1000)}"
            self._lessons.append(
                {
                    "id": promoted_id,
                    "key": global_key,
                    "trigger": trigger,
                    "bad_action": str(supporting_lessons[-1].get("bad_action", "")),
                    "better_action": better_action,
                    "scope": "global",
                    "session_key": "",
                    "actor_key": "",
                    "source": "auto_promoted",
                    "confidence": min(10, max(self.min_lesson_confidence, len(actor_keys) + 1)),
                    "hits": max(1, support_hits),
                    "enabled": True,
                    "created_at": now,
                    "updated_at": now,
                    "last_applied_at": "",
                    "promoted_global_key": "",
                }
            )

        for lesson in supporting_lessons:
            lesson["promoted_global_key"] = global_key

        self._audit_buffer.append(
            {
                "type": "lesson_promoted",
                "at": now,
                "trigger": trigger,
                "global_id": promoted_id,
                "actor_count": len(actor_keys),
            }
        )
