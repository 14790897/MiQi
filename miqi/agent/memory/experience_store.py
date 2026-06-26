"""Unified read-only facade over MemoryStore (facts + rules) and TraceStore (history)."""

from __future__ import annotations

from typing import Literal

EntryType = Literal["fact", "rule", "trace"]


class ExperienceStore:
    """Aggregates facts, rules, and traces into a single ExperienceEntry list."""

    def __init__(self, memory_store, trace_store):
        self._memory = memory_store
        self._trace = trace_store

    def list_entries(
        self,
        type: EntryType | None = None,
        scope: str | None = None,
        session_key: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        entries: list[dict] = []

        if type is None or type == "fact":
            for item in self._memory._snapshot_store.list_items(
                session_key=session_key, limit=limit
            ):
                entries.append({
                    "id": str(item.get("id", "")),
                    "type": "fact",
                    "title": str(item.get("text", ""))[:80],
                    "content": str(item.get("text", "")),
                    "confidence": 0,
                    "enabled": True,
                    "scope": scope or "global",
                    "source": str(item.get("source", "auto")),
                    "session_key": str(item.get("session_key", "")),
                    "created_at": _parse_ts(item.get("created_at")),
                    "updated_at": _parse_ts(item.get("updated_at")),
                    "metadata": {},
                })

        if type is None or type == "rule":
            for lesson in self._memory._lesson_store._lessons:
                if lesson.get("state") == "archived":
                    continue
                if scope and lesson.get("scope") != scope:
                    continue
                if session_key and lesson.get("session_key") and lesson.get("session_key") != session_key:
                    continue
                entries.append({
                    "id": str(lesson.get("id", "")),
                    "type": "rule",
                    "title": str(lesson.get("trigger", "")),
                    "content": f"{lesson.get('bad_action', '')} → {lesson.get('better_action', '')}",
                    "confidence": int(lesson.get("confidence", 0)),
                    "enabled": bool(lesson.get("enabled", True)),
                    "scope": str(lesson.get("scope", "global")),
                    "source": str(lesson.get("source", "auto")),
                    "session_key": str(lesson.get("session_key", "")),
                    "created_at": _parse_ts(lesson.get("created_at")),
                    "updated_at": _parse_ts(lesson.get("updated_at")),
                    "metadata": {
                        "bad_action": str(lesson.get("bad_action", "")),
                        "better_action": str(lesson.get("better_action", "")),
                        "hits": int(lesson.get("hits", 0)),
                        "state": str(lesson.get("state", "active")),
                    },
                })

        if type is None or type == "trace":
            traces = self._trace.list_recent(n=max(1, limit))
            for trace in traces:
                if session_key and trace.session_id != session_key:
                    continue
                entries.append({
                    "id": trace.trace_hash,
                    "type": "trace",
                    "title": trace.task_name,
                    "content": trace.goal,
                    "confidence": 0,
                    "enabled": True,
                    "scope": "session",
                    "source": "auto",
                    "session_key": trace.session_id,
                    "created_at": trace.created_at,
                    "updated_at": trace.ended_at or trace.created_at,
                    "metadata": {
                        "outcome": trace.outcome,
                        "outcome_notes": trace.outcome_notes,
                        "parent_hash": trace.parent_hash,
                        "tool_count": len(trace.tool_calls),
                        "tool_calls": [
                            {
                                "tool_name": tc.tool_name,
                                "args_summary": tc.args_summary,
                                "result_summary": tc.result_summary,
                                "timestamp": tc.timestamp,
                            }
                            for tc in trace.tool_calls
                        ],
                    },
                })

        entries.sort(key=lambda e: e["created_at"], reverse=True)
        return entries[: max(1, limit)]

    def delete_entry(self, type: EntryType, entry_id: str) -> bool:
        if type == "rule":
            ok = self._memory._lesson_store.unlearn_by_id(entry_id)
            if ok:
                self._memory._lesson_store.flush()
            return ok
        elif type == "fact":
            return self._memory._snapshot_store.delete_item(entry_id)
        elif type == "trace":
            try:
                with self._trace._lock:
                    self._trace._conn.execute(
                        "DELETE FROM task_traces WHERE trace_hash = ?", (entry_id,)
                    )
                    self._trace._conn.commit()
                return True
            except Exception:
                return False
        return False

    def toggle_entry(self, type: EntryType, entry_id: str, enabled: bool) -> bool:
        if type == "rule":
            for lesson in self._memory._lesson_store._lessons:
                if str(lesson.get("id", "")) == entry_id:
                    lesson["enabled"] = enabled
                    lesson["updated_at"] = _now_iso()
                    self._memory._lesson_store._dirty = True
                    self._memory._lesson_store.flush()
                    return True
            return False
        return False

    def search_entries(
        self, query: str, type: EntryType | None = None, limit: int = 10
    ) -> list[dict]:
        all_entries = self.list_entries(type=type, limit=1000)
        q = query.lower()
        matched = []
        for e in all_entries:
            if q in e["title"].lower() or q in e["content"].lower():
                matched.append(e)
            if len(matched) >= limit:
                break
        return matched


def _parse_ts(val) -> float:
    """Parse a timestamp from either ISO string or float."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str) and val:
        import time
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return time.mktime(time.strptime(val, fmt))
            except (ValueError, OverflowError):
                continue
        return 0.0
    return 0.0


def _now_iso() -> str:
    import time as _time
    return _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime())
