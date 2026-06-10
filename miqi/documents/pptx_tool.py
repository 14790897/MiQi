"""PowerPoint (.pptx) read/write tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.agent.tools.base import Tool


class PptxReadTool(Tool):
    """Read the content of a PowerPoint (.pptx) presentation."""

    name = "pptx_read"
    description = "Read and extract text content from a PowerPoint (.pptx) file."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the .pptx file to read",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        file_path = Path(kwargs["file_path"])
        if not file_path.exists():
            return f"Error: file not found: {file_path}"
        try:
            from pptx import Presentation
            prs = Presentation(str(file_path))
            lines = [f"Presentation: {len(prs.slides)} slides", ""]
            for i, slide in enumerate(prs.slides, 1):
                lines.append(f"## Slide {i}")
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            text = para.text.strip()
                            if text:
                                lines.append(text)
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading {file_path.name}: {e}"


class PptxWriteTool(Tool):
    """Create a PowerPoint (.pptx) presentation."""

    name = "pptx_write"
    description = (
        "Create a new PowerPoint (.pptx) file. "
        "Provide 'slides' as [{title: str, content: str}, ...]."
    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path for the output .pptx file",
                },
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["title", "content"],
                    },
                    "description": "List of slides with title and content",
                },
            },
            "required": ["file_path", "slides"],
        }

    async def execute(self, **kwargs: Any) -> str:
        from pptx import Presentation
        from pptx.util import Inches

        file_path = Path(kwargs["file_path"])
        slides = kwargs["slides"]

        try:
            prs = Presentation()
            for slide_data in slides:
                slide_layout = prs.slide_layouts[1]  # Title and Content
                slide = prs.slides.add_slide(slide_layout)
                title = slide.shapes.title
                if title:
                    title.text = slide_data.get("title", "")
                # Add content to body placeholder
                body = slide.placeholders[1] if len(slide.placeholders) > 1 else None
                if body and hasattr(body, "text_frame"):
                    body.text_frame.text = slide_data.get("content", "")

            file_path.parent.mkdir(parents=True, exist_ok=True)
            prs.save(str(file_path))
            return f"Created: {file_path} ({len(slides)} slides)"
        except Exception as e:
            return f"Error writing {file_path.name}: {e}"
