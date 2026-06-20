"""Runtime-owned tool registry factory.

Historical: Creates a fully populated ToolRegistry without depending on the
legacy AgentLoop. Replaces AgentLoop._register_default_tools() for
runtime-owned sessions.

Registration order is kept stable so model tool specs remain deterministic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.agent.tools.registry import ToolRegistry


def create_runtime_tool_registry(
    *,
    config: Any,
    workspace: Path,
    provider: Any = None,
    bus: Any = None,
    approval_callback: Any = None,
    sandbox_manager: Any = None,
    cron_service: Any = None,
    subagent_manager: Any = None,
    memory_store: Any = None,
    trace_store: Any = None,
    session_manager: Any = None,
    plan_tracker: Any = None,
) -> ToolRegistry:
    """Create the runtime-owned ToolRegistry.

    Historical: This replaces RuntimeServices' dependency on the legacy
    AgentLoop._setup_tools().
    Registration order is kept stable so model tool specs remain deterministic.

    Args:
        config: MiQi Config object (config.schema.Config).
        workspace: Session workspace directory.
        provider: LLM provider (needed for SubagentManager if spawn is desired).
        bus: MessageBus (needed for MessageTool).
        approval_callback: Optional approval callback for ExecTool.
        sandbox_manager: Optional sandbox manager for filesystem isolation.
        cron_service: Optional CronService for cron tool.
        subagent_manager: Optional SubagentManager for spawn tool.
        memory_store: Optional MemoryStore for memory tool.
        trace_store: Optional TraceStore for task_begin/end/trace_search tools.
        session_manager: Optional SessionManager for session_search tool.
        plan_tracker: Optional PlanTracker for plan_create/plan_update tools.

    Returns:
        ToolRegistry populated with the runtime's default tool set.
    """
    from miqi.utils.helpers import safe_filename

    defaults = getattr(config, "agents", None)
    defaults = getattr(defaults, "defaults", None) if defaults is not None else None

    # Resolve session-key-dependent paths (Historical: mirrors the legacy
    # AgentLoop._register_default_tools)
    _session_key = getattr(config, "_session_key", "") or ""
    _snap_dir: Path | None = None
    _work_dir: Path | None = None
    _write_workspace: Path = workspace

    session_config = getattr(defaults, "session_config", None) if defaults is not None else None
    if not session_config:
        session_config = getattr(config, "agents", None)
        session_config = getattr(session_config, "sessions", None) if session_config is not None else None

    if _session_key:
        safe_key = safe_filename(_session_key.replace(":", "_"))
        _snap_dir = workspace / "sessions" / safe_key / "snapshots"
        _snap_dir.mkdir(parents=True, exist_ok=True)
        if session_config is not None and getattr(session_config, "session_workspace_enabled", False):
            _work_dir = workspace / "sessions" / safe_key / "files"
            _work_dir.mkdir(parents=True, exist_ok=True)
            from miqi.utils.helpers import ensure_sessions_gitignored

            ensure_sessions_gitignored(workspace)

    if _work_dir is not None:
        _write_workspace = _work_dir

    # Resolve config sections
    tools_cfg = getattr(config, "tools", None)
    restrict_to_workspace = getattr(tools_cfg, "restrict_to_workspace", False) if tools_cfg is not None else False

    exec_cfg = getattr(tools_cfg, "exec", None) if tools_cfg is not None else None
    web_cfg = getattr(tools_cfg, "web", None) if tools_cfg is not None else None
    paper_cfg = getattr(tools_cfg, "papers", None) if tools_cfg is not None else None

    allowed_dir = workspace if restrict_to_workspace else None

    _sbm = sandbox_manager

    # ── Core tools (always registered) ──────────────────────────────────
    from miqi.agent.tools.filesystem import (
        EditFileTool,
        ListDirTool,
        ReadFileTool,
        WriteFileTool,
    )
    from miqi.agent.tools.shell import ExecTool

    registry = ToolRegistry()

    # 1. Filesystem tools
    for cls in (ReadFileTool, ListDirTool):
        registry.register(cls(workspace=workspace, allowed_dir=allowed_dir, sandbox_manager=_sbm))
    registry.register(
        WriteFileTool(
            workspace=_write_workspace,
            allowed_dir=allowed_dir,
            snapshot_dir=_snap_dir,
            sandbox_manager=_sbm,
        )
    )
    registry.register(
        EditFileTool(
            workspace=_write_workspace,
            allowed_dir=allowed_dir,
            snapshot_dir=_snap_dir,
            sandbox_manager=_sbm,
        )
    )

    # 2. Exec tool
    registry.register(
        ExecTool(
            working_dir=str(_work_dir or workspace),
            timeout=getattr(exec_cfg, "timeout", 60) if exec_cfg is not None else 60,
            restrict_to_workspace=restrict_to_workspace,
            env_passthrough=list(getattr(exec_cfg, "env_passthrough", [])) if exec_cfg is not None else [],
            approval_callback=approval_callback,
            sandbox_manager=_sbm,
        )
    )

    # 3. Web tools
    from miqi.agent.tools.web import WebFetchTool, WebSearchTool

    if web_cfg is not None:
        search_cfg = getattr(web_cfg, "search", None)
        fetch_cfg = getattr(web_cfg, "fetch", None)
    else:
        search_cfg = None
        fetch_cfg = None

    registry.register(
        WebSearchTool(
            provider=getattr(search_cfg, "provider", "brave") if search_cfg is not None else "brave",
            api_key=getattr(search_cfg, "api_key", None) if search_cfg is not None else None,
            max_results=getattr(search_cfg, "max_results", 5) if search_cfg is not None else 5,
            ollama_api_key=getattr(search_cfg, "ollama_api_key", None) if search_cfg is not None else None,
            ollama_api_base=getattr(search_cfg, "ollama_api_base", None) if search_cfg is not None else None,
        )
    )
    registry.register(
        WebFetchTool(
            provider=getattr(fetch_cfg, "provider", "builtin") if fetch_cfg is not None else "builtin",
            ollama_api_key=getattr(fetch_cfg, "ollama_api_key", None) if fetch_cfg is not None else None,
            ollama_api_base=getattr(fetch_cfg, "ollama_api_base", None) if fetch_cfg is not None else None,
        )
    )

    # 4. Paper tools
    from miqi.agent.tools.papers import PaperDownloadTool, PaperGetTool, PaperSearchTool

    paper_provider = getattr(paper_cfg, "provider", "hybrid") if paper_cfg is not None else "hybrid"
    paper_api_key = getattr(paper_cfg, "semantic_scholar_api_key", None) if paper_cfg is not None else None
    paper_timeout = getattr(paper_cfg, "timeout_seconds", 20) if paper_cfg is not None else 20
    paper_default_limit = getattr(paper_cfg, "default_limit", 8) if paper_cfg is not None else 8
    paper_max_limit = getattr(paper_cfg, "max_limit", 20) if paper_cfg is not None else 20

    registry.register(
        PaperSearchTool(
            provider=paper_provider,
            semantic_scholar_api_key=paper_api_key,
            timeout_seconds=paper_timeout,
            default_limit=paper_default_limit,
            max_limit=paper_max_limit,
        )
    )
    registry.register(
        PaperGetTool(
            provider=paper_provider,
            semantic_scholar_api_key=paper_api_key,
            timeout_seconds=paper_timeout,
        )
    )
    registry.register(
        PaperDownloadTool(
            workspace=workspace,
            provider=paper_provider,
            semantic_scholar_api_key=paper_api_key,
            timeout_seconds=paper_timeout,
        )
    )

    # 5. Skill manage tool
    from miqi.agent.tools.skill_manage import SkillManageTool

    registry.register(SkillManageTool(workspace=workspace))

    # 6. Office document tools
    from miqi.documents.docx_tool import DocxReadTool, DocxWriteTool
    from miqi.documents.pptx_tool import PptxReadTool, PptxWriteTool
    from miqi.documents.xlsx_tool import XlsxReadTool, XlsxWriteTool

    registry.register(DocxReadTool())
    # Office write tools always write inside the workspace, independently
    # of the `restrict_to_workspace` config (which only controls
    # WriteFileTool / EditFileTool).
    registry.register(DocxWriteTool(workspace=_write_workspace, allowed_dir=_write_workspace))
    registry.register(PptxReadTool())
    registry.register(PptxWriteTool(workspace=_write_workspace, allowed_dir=_write_workspace))
    registry.register(XlsxReadTool())
    registry.register(XlsxWriteTool(workspace=_write_workspace, allowed_dir=_write_workspace))

    # ── Optional tools (require external dependencies) ─────────────────

    # 7. Memory tool (requires MemoryStore)
    if memory_store is not None:
        from miqi.agent.tools.memory import MemoryTool

        registry.register(MemoryTool(memory_store=memory_store))

    # 8. Task trace tools (require TraceStore)
    if trace_store is not None:
        from miqi.agent.tools.task_trace import TaskBeginTool, TaskEndTool, TraceSearchTool

        registry.register(TaskBeginTool(trace_store=trace_store))
        registry.register(TaskEndTool(trace_store=trace_store))
        registry.register(TraceSearchTool(trace_store=trace_store))

    # 9. Session search tool (requires MemoryStore + SessionManager)
    if memory_store is not None and session_manager is not None:
        from miqi.agent.tools.session_search import SessionSearchTool

        registry.register(SessionSearchTool(memory=memory_store, session_manager=session_manager))

    # 10. Message tool (requires MessageBus)
    if bus is not None:
        from miqi.agent.tools.message import MessageTool

        registry.register(MessageTool(send_callback=bus.publish_outbound))

    # 11. Spawn tool (requires SubagentManager)
    if subagent_manager is not None:
        from miqi.agent.tools.spawn import SpawnTool

        registry.register(
            SpawnTool(
                manager=subagent_manager,
                agent_control=None,  # Wired later by RuntimeServices
                event_emitter=None,
            )
        )

    # 12. Cron tool (requires CronService)
    if cron_service is not None:
        from miqi.agent.tools.cron import CronTool

        registry.register(CronTool(cron_service))

    # 13. Plan tools (require PlanTracker)
    if plan_tracker is not None:
        from miqi.plan.plan_tool import PlanCreateTool, PlanUpdateTool

        registry.register(PlanCreateTool(tracker=plan_tracker))
        registry.register(PlanUpdateTool(tracker=plan_tracker))

    return registry
