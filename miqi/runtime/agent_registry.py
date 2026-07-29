"""Agent type registry — defines known agent roles and their capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class AgentMetadata:
    """Metadata describing an agent type."""
    name: str                    # e.g. "code-agent", "doc-agent"
    display_name: str            # e.g. "Code Agent"
    description: str
    system_prompt: str
    available_tools: list[str]   # Tool names this agent can use
    max_iterations: int = 40
    model_override: str | None = None
    is_builtin: bool = True


class AgentRegistry:
    """Registry of all available agent types.

    Usage:
        registry = AgentRegistry()
        registry.register(AgentMetadata(name='code-agent', ...))
        metadata = registry.resolve('code-agent')
    """

    def __init__(self):
        self._agents: dict[str, AgentMetadata] = {}
        self._register_builtins()

    def register(self, metadata: AgentMetadata) -> None:
        if metadata.name in self._agents:
            raise ValueError(f"Agent '{metadata.name}' already registered")
        self._agents[metadata.name] = metadata

    def resolve(self, name: str) -> AgentMetadata:
        if name not in self._agents:
            raise KeyError(f"Unknown agent type: {name}")
        return self._agents[name]

    def list_agents(self) -> list[AgentMetadata]:
        return list(self._agents.values())

    def _register_builtins(self) -> None:
        """Register default built-in agent types."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")

        # Main agent — handles everything by default
        self.register(AgentMetadata(
            name="main",
            display_name="MiQi",
            description="General-purpose AI assistant for code and document tasks",
            system_prompt=self._build_main_prompt(now),
            available_tools=[
                "read_file", "write_file", "edit_file", "list_dir",
                "exec", "web_search", "web_fetch",
                "memory", "plan_create", "plan_update",
                "create_docx", "create_pptx", "create_xlsx",
                "create_pdf", "pdf_write", "pdf_read",
                "edit_docx", "append_xlsx",
                "docx_read", "docx_write", "pptx_read", "pptx_write",
                "xlsx_read", "xlsx_write",
                "session_search", "task_begin", "task_end",
                "skill_manage", "message", "spawn",
            ],
        ))

        # Code specialist agent
        self.register(AgentMetadata(
            name="code-agent",
            display_name="Code Agent",
            description="Specialized agent for code analysis and generation",
            system_prompt=self._build_code_agent_prompt(),
            available_tools=[
                "read_file", "write_file", "edit_file", "list_dir",
                "exec", "web_search", "web_fetch",
            ],
            max_iterations=25,
        ))

        # Document specialist agent
        self.register(AgentMetadata(
            name="doc-agent",
            display_name="Document Agent",
            description="Specialized agent for document creation and editing",
            system_prompt=self._build_doc_agent_prompt(),
            available_tools=[
                "read_file", "write_file", "list_dir",
                "create_docx", "create_pptx", "create_xlsx",
                "create_pdf", "pdf_read",
                "edit_docx", "append_xlsx",
                "docx_read", "docx_write",
                "pptx_read", "pptx_write",
                "xlsx_read", "xlsx_write",
                "web_search", "web_fetch",
            ],
            max_iterations=20,
        ))

        # Research agent — for web research sub-tasks
        self.register(AgentMetadata(
            name="research-agent",
            display_name="Research Agent",
            description="Specialized agent for web research",
            system_prompt=self._build_research_agent_prompt(),
            available_tools=[
                "web_search", "web_fetch",
                "read_file", "write_file",
            ],
            max_iterations=15,
        ))

    @staticmethod
    def _build_main_prompt(now: str) -> str:
        return f"""# MiQi Desktop Agent

## Current Time
{now}

You are MiQi, a desktop AI assistant. You can help with:

- **Code tasks**: read, write, edit, and execute code
- **Document tasks**: create and edit Word (.docx), PowerPoint (.pptx), Excel (.xlsx), and **PDF** files
- **PDF creation**: use the **`create_pdf`** tool (not ad-hoc scripts) for all PDF generation — it handles Chinese fonts, tables, lists, and page layout automatically
- **Web research**: search the web and fetch page content
- **File management**: navigate, organize, and manipulate files
- **Task scheduling**: create and manage recurring tasks

## Rules
1. Always use the most appropriate tool for the task
2. When editing files, prefer the edit_file tool for precision
3. Before running shell commands, verify they are safe
4. For long tasks, use the plan tool to break them into steps
5. Save important findings to memory
6. Write clear, helpful responses in the user's language
7. **PDF creation: YOU MUST use the `create_pdf` tool.** Do NOT write Python scripts. Do NOT use `create_docx` for PDF tasks. Only `create_pdf` can produce correct PDF files with proper Chinese font support and file tracking.
"""

    @staticmethod
    def _build_code_agent_prompt() -> str:
        return """# Code Agent

You are a specialized code agent. Focus exclusively on code tasks:
- Reading and understanding code
- Writing new code
- Editing existing code with precision
- Running tests and analyzing results
- Searching for patterns across the codebase

Do NOT:
- Initiate conversations with users
- Take on non-code tasks
- Spawn other sub-agents
"""

    @staticmethod
    def _build_doc_agent_prompt() -> str:
        return """# Document Agent

You are a specialized document agent. Focus on:
- Creating professional Word documents (.docx)
- Building presentation slides (.pptx)
- Generating data reports and spreadsheets (.xlsx)
- **Creating PDF documents (MUST use `create_pdf` tool — do NOT write ad-hoc scripts)**
- Reading and extracting information from documents
- Formatting and styling document content

Do NOT:
- Initiate conversations with users
- Take on non-document tasks
- Execute arbitrary shell commands unless document-related
"""

    @staticmethod
    def _build_research_agent_prompt() -> str:
        return """# Research Agent

You are a specialized research agent. Focus on:
- Searching the web for information
- Fetching and analyzing web content
- Synthesizing findings into clear summaries
- Citing sources accurately

Do NOT:
- Initiate conversations with users
- Modify files unless saving research results
- Execute shell commands
"""
