"""Word document (.docx) read/write tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.agent.tools.base import Tool


class DocxReadTool(Tool):
    """Read the text content of a Word (.docx) document."""

    name = "docx_read"
    description = "Read and extract text content from a Word (.docx) document."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the .docx file to read",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        file_path = Path(kwargs["file_path"])
        if not file_path.exists():
            return f"Error: file not found: {file_path}"
        try:
            from docx import Document
            doc = Document(str(file_path))
            paragraphs = []
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append(para.text)
            return "\n\n".join(paragraphs)
        except Exception as e:
            return f"Error reading {file_path.name}: {e}"


def _resolve_output_path(
    file_path: str,
    workspace: Path | None,
    allowed_dir: Path | None,
) -> Path:
    """Resolve an output path and enforce workspace/directory bounds.

    Office document write tools always write inside the workspace:
    - Relative paths are resolved against *workspace*.
    - If *allowed_dir* is ``None`` but *workspace* is set, *workspace*
      is used as the effective boundary (defense-in-depth default).
    - Absolute paths outside the effective boundary are rejected.

    Raises:
        PermissionError: if the resolved path is outside the effective boundary.
    """
    p = Path(file_path).expanduser()
    if not p.is_absolute() and workspace is not None:
        p = workspace / p
    resolved = p.resolve()

    # Defense-in-depth: when no explicit allowed_dir is given, office
    # write tools default to workspace as the boundary.  This is
    # independent of the `restrict_to_workspace` config (which only
    # controls WriteFileTool / EditFileTool).
    effective_dir = allowed_dir
    if effective_dir is None and workspace is not None:
        effective_dir = workspace.resolve()

    if effective_dir is not None:
        try:
            resolved.relative_to(effective_dir.resolve())
        except ValueError:
            raise PermissionError(
                f"Path '{file_path}' resolves outside allowed directory "
                f"'{effective_dir}'"
            )
    return resolved


class DocxWriteTool(Tool):
    """Create or overwrite a Word (.docx) document."""

    name = "docx_write"
    description = (
        "Create a new Word (.docx) document with the given content. "
        "Content is markdown-like: each line is a paragraph, "
        "'# ' lines are headings."
    )

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
    ):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path for the output .docx file",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown-like content. Each line = paragraph. '# Title' = heading.",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, **kwargs: Any) -> str:
        from docx import Document

        raw_path = kwargs["file_path"]
        content = kwargs["content"]

        try:
            file_path = _resolve_output_path(
                raw_path, self._workspace, self._allowed_dir,
            )
        except PermissionError as e:
            return f"Error: Permission denied: {e}"

        try:
            doc = Document()
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("# "):
                    doc.add_heading(line[2:], level=1)
                elif line.startswith("## "):
                    doc.add_heading(line[3:], level=2)
                else:
                    doc.add_paragraph(line)

            file_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(file_path))
            return f"Created: {file_path} ({len(content)} chars)"
        except Exception as e:
            return f"Error writing {raw_path}: {e}"
