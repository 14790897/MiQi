"""Agent tools for task trace workflows."""

from __future__ import annotations

import json
from typing import Any

from miqi.agent.tools.base import Tool
from miqi.agent.trace.store import TraceStore


class TaskBeginTool(Tool):
    def __init__(self, trace_store: TraceStore):
        self._store = trace_store

    @property
    def name(self) -> str:
        return "task_begin"

    @property
    def description(self) -> str:
        return (
            "Override the auto-generated trace name for this turn. Use when starting a "
            "complex multi-step task to give it a meaningful name and goal description. "
            "The system already auto-begins a trace for each user turn; calling this tool "
            "replaces the auto-generated task_name and goal."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_name": {
                    "type": "string",
                    "description": "Short slug, e.g. 'fetch-arxiv-paper'.",
                },
                "goal": {"type": "string", "description": "Natural language objective."},
                "parent_hash": {
                    "type": "string",
                    "description": (
                        "Optional. Hash of a prior trace to inherit from as parent. "
                        "Use to explicitly link cross-session lineage. "
                        "If omitted, the previous trace in this session is used automatically."
                    ),
                },
            },
            "required": ["task_name", "goal"],
        }

    async def execute(
        self,
        *,
        task_name: str,
        goal: str,
        parent_hash: str | None = None,
        session_id: str = "default",
        **_: Any,
    ) -> str:
        task_id = self._store.begin_task(session_id, task_name, goal, parent_hash=parent_hash or None)
        return json.dumps({"ok": True, "task_id": task_id})


class TaskEndTool(Tool):
    def __init__(self, trace_store: TraceStore):
        self._store = trace_store

    @property
    def name(self) -> str:
        return "task_end"

    @property
    def description(self) -> str:
        return (
            "End the currently open task and record outcome. "
            "After ending, returns up to 3 similar historical traces for reflection."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": ["success", "partial", "failure"]},
                "notes": {
                    "type": "string",
                    "description": "Why it succeeded/failed; lessons learned.",
                },
            },
            "required": ["outcome"],
        }

    async def execute(
        self,
        *,
        outcome: str,
        notes: str = "",
        session_id: str = "default",
        **_: Any,
    ) -> str:
        trace_hash = self._store.end_task(session_id, outcome, notes, tool_calls=[])
        if not trace_hash:
            return json.dumps({"ok": False, "error": "no open task"})
        similar = self._store.search_traces(notes or "", limit=3)
        return json.dumps(
            {
                "ok": True,
                "hash": trace_hash,
                "similar": [
                    {
                        "hash": t.trace_hash,
                        "task_name": t.task_name,
                        "goal": t.goal,
                        "outcome": t.outcome,
                        "score": round(t.similarity_score, 3),
                    }
                    for t in similar
                ],
            },
            ensure_ascii=False,
        )


class TraceSearchTool(Tool):
    def __init__(self, trace_store: TraceStore):
        self._store = trace_store

    @property
    def name(self) -> str:
        return "trace_search"

    @property
    def description(self) -> str:
        return (
            "Search history for similar tasks. Use this proactively BEFORE starting a "
            "complex new task to learn from past workflows."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    async def execute(self, *, query: str, **_: Any) -> str:
        results = self._store.search_traces(query, limit=5)
        return json.dumps(
            {
                "results": [
                    {
                        "hash": t.trace_hash,
                        "task_name": t.task_name,
                        "goal": t.goal,
                        "outcome": t.outcome,
                        "score": round(t.similarity_score, 3),
                        "tool_chain": [s.tool_name for s in t.tool_calls],
                        "notes": t.outcome_notes,
                    }
                    for t in results
                ]
            },
            ensure_ascii=False,
        )
