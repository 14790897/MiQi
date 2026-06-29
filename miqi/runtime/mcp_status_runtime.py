"""Runtime-owned MCP server status snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class McpServerStatus:
    name: str
    status: str = "not_started"
    error: str | None = None
    thread_id: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    resource_templates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "error": self.error,
            "threadId": self.thread_id,
            "config": dict(self.config),
            "tools": list(self.tools),
            "resources": list(self.resources),
            "resourceTemplates": list(self.resource_templates),
        }


class McpStatusRuntime:
    def __init__(self) -> None:
        self._statuses: dict[tuple[str | None, str], McpServerStatus] = {}

    def replace_config_servers(self, servers: dict[str, Any]) -> None:
        for name, cfg in servers.items():
            payload = cfg.model_dump() if hasattr(cfg, "model_dump") else dict(cfg)
            self._statuses[(None, name)] = McpServerStatus(
                name=name,
                status="not_started",
                config=payload,
            )

    def replace_plugin_servers(self, servers: list[dict[str, Any]]) -> None:
        for cfg in servers:
            name = str(cfg.get("name", ""))
            if not name:
                continue
            self._statuses[(None, name)] = McpServerStatus(
                name=name,
                status="not_started",
                config=dict(cfg),
            )

    def mark_starting(self, name: str, *, thread_id: str | None) -> None:
        status = self._get_or_create(name, thread_id)
        status.status = "starting"
        status.error = None

    def mark_ready(
        self,
        name: str,
        *,
        thread_id: str | None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        status = self._get_or_create(name, thread_id)
        status.status = "ready"
        status.error = None
        status.tools = list(tools or [])

    def mark_failed(self, name: str, error: str, *, thread_id: str | None) -> None:
        status = self._get_or_create(name, thread_id)
        status.status = "failed"
        status.error = error

    def list_statuses(self, *, thread_id: str | None = None) -> list[McpServerStatus]:
        result = [
            status for (tid, _name), status in self._statuses.items()
            if thread_id is None or tid == thread_id
        ]
        return sorted(result, key=lambda item: item.name)

    def _get_or_create(self, name: str, thread_id: str | None) -> McpServerStatus:
        key = (thread_id, name)
        if key not in self._statuses:
            self._statuses[key] = McpServerStatus(name=name, thread_id=thread_id)
        return self._statuses[key]
