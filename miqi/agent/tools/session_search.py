"""Session search tool — search past conversations for relevant context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from miqi.agent.tools.base import Tool


class SessionSearchTool(Tool):
    """Tool for searching past conversation sessions for relevant context."""

    def __init__(self, memory: object, session_manager: object):
        self._memory = memory
        self._session_manager = session_manager

    @property
    def name(self) -> str:
        return "session_search"

    @property
    def description(self) -> str:
        return (
            "Search past conversations for relevant context. "
            "Use BEFORE asking the user to repeat something you may have discussed "
            "before. If no query is given, returns a summary of the most recent sessions."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional. FTS5 search query. Omit to list recent sessions.",
                },
            },
            "required": [],
        }

    async def execute(self, query: str = "") -> str:
        if not query or not query.strip():
            return self._list_recent_sessions()

        return self._search(query.strip())

    def _list_recent_sessions(self) -> str:
        sessions = self._session_manager.list_sessions()
        recent = sessions[:5]
        if not recent:
            return '{"results": []}'

        results = []
        for s in recent:
            results.append(
                {
                    "session_key": s.get("key", "?"),
                    "role": "summary",
                    "snippet": s.get("key", "?"),
                    "score": 0,
                }
            )
        return json.dumps({"results": results}, ensure_ascii=False)

    def _search(self, query: str) -> str:
        # Try FTS5 search via SQLite store first
        sqlite_store = getattr(self._memory, "_sqlite_store", None)
        if sqlite_store is not None:
            try:
                hits = sqlite_store.search_messages(query, limit=10)  # type: ignore[union-attr]
                if hits:
                    return json.dumps({"results": hits}, ensure_ascii=False)
            except Exception:
                pass

        # Fallback: scan JSONL sessions with substring matching
        sessions = self._session_manager.list_sessions()
        results: list[dict[str, Any]] = []
        query_lower = query.lower()

        for s in sessions:
            path = Path(s.get("path", ""))
            if not path.exists():
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if data.get("_type") == "metadata":
                            continue
                        content = str(data.get("content", ""))
                        if query_lower in content.lower():
                            snippet = content
                            if len(snippet) > 200:
                                idx = content.lower().find(query_lower)
                                start = max(0, idx - 80)
                                end = min(len(content), idx + len(query) + 80)
                                snippet = content[start:end]
                                if start > 0:
                                    snippet = "..." + snippet
                                if end < len(content):
                                    snippet = snippet + "..."
                            results.append(
                                {
                                    "session_key": s.get("key", "?"),
                                    "role": data.get("role", "?"),
                                    "snippet": snippet,
                                    "score": 0,
                                }
                            )
                        if len(results) >= 10:
                            break
                if len(results) >= 10:
                    break
            except Exception:
                continue

        return json.dumps({"results": results}, ensure_ascii=False)
