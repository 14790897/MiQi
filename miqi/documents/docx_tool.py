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


class DocxWriteTool(Tool):
    """Create or overwrite a Word (.docx) document."""

    name = "docx_write"
    description = (
        "Create a new Word (.docx) document with the given content. "
        "Content is markdown-like: each line is a paragraph, "
        "'# ' lines are headings."
    )

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
        from docx.shared import Pt

        file_path = Path(kwargs["file_path"])
        content = kwargs["content"]

        try:
            doc = Document()
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("# "):
                    heading = doc.add_heading(line[2:], level=1)
                elif line.startswith("## "):
                    heading = doc.add_heading(line[3:], level=2)
                else:
                    doc.add_paragraph(line)

            file_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(file_path))
            return f"Created: {file_path} ({len(content)} chars)"
        except Exception as e:
            return f"Error writing {file_path.name}: {e}"
