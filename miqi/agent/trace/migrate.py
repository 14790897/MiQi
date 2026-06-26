"""Migration helpers for legacy self-improvement lessons."""

from __future__ import annotations

import json
import time
from pathlib import Path

from miqi.agent.trace.model import TaskTrace
from miqi.agent.trace.store import TraceStore


def migrate_lessons_to_traces(lessons_file: Path, store: TraceStore) -> int:
    """Convert legacy LESSONS.jsonl rows into minimal task traces."""
    if not lessons_file.exists():
        return 0

    count = 0
    with lessons_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lesson = json.loads(line)
            lesson_id = lesson["id"]
            trace_hash = f"lesson:{lesson_id}"
            if store.get_trace(trace_hash) is not None:
                continue

            goal = f"Avoid: {lesson.get('bad_action', '')}"
            trace = TaskTrace(
                trace_hash=trace_hash,
                parent_hash=None,
                session_id=lesson.get("actor_key", "migrated"),
                task_name=f"lesson-{lesson.get('trigger', 'unknown')}",
                goal=goal,
                tool_calls=[],
                outcome="success" if lesson.get("enabled", True) else "failure",
                outcome_notes=lesson.get("better_action", ""),
                embedding=None,
                created_at=lesson.get("created_at", time.time()),
                ended_at=lesson.get("updated_at", time.time()),
                metadata={
                    "source": "legacy_lesson",
                    "trigger": lesson.get("trigger"),
                },
            )
            store.upsert_trace(trace)
            count += 1
    return count
