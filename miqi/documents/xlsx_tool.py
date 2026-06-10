"""Excel (.xlsx) read/write tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.agent.tools.base import Tool


class XlsxReadTool(Tool):
    """Read data from an Excel (.xlsx) spreadsheet."""

    name = "xlsx_read"
    description = "Read and extract data from an Excel (.xlsx) file. Returns sheet names and content."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the .xlsx file to read",
                },
                "sheet_name": {
                    "type": "string",
                    "description": "Optional: specific sheet name to read. Reads first sheet if omitted.",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        file_path = Path(kwargs["file_path"])
        if not file_path.exists():
            return f"Error: file not found: {file_path}"
        try:
            from openpyxl import load_workbook
            wb = load_workbook(str(file_path), read_only=True, data_only=True)
            sheet_name = kwargs.get("sheet_name")
            if sheet_name and sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
            else:
                ws = wb.active

            lines = [f"Sheet: {ws.title} ({ws.max_row} rows × {ws.max_column} cols)", ""]
            for row in ws.iter_rows(values_only=True, max_row=min(ws.max_row, 200)):
                cells = [str(c) if c is not None else "" for c in row]
                lines.append(" | ".join(cells))
            wb.close()

            if ws.max_row > 200:
                lines.append(f"\n... ({ws.max_row - 200} more rows)")

            return "\n".join(lines)
        except Exception as e:
            return f"Error reading {file_path.name}: {e}"


class XlsxWriteTool(Tool):
    """Create an Excel (.xlsx) spreadsheet."""

    name = "xlsx_write"
    description = (
        "Create a new Excel (.xlsx) file. "
        "Provide 'sheets' as {sheet_name: [[row1_col1, row1_col2], [row2_col1, ...]]}."
    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path for the output .xlsx file",
                },
                "sheets": {
                    "type": "object",
                    "description": "Dict of sheet_name → list of row lists",
                },
            },
            "required": ["file_path", "sheets"],
        }

    async def execute(self, **kwargs: Any) -> str:
        from openpyxl import Workbook

        file_path = Path(kwargs["file_path"])
        sheets = kwargs["sheets"]

        try:
            wb = Workbook()
            wb.remove(wb.active)  # Remove default sheet

            first = True
            for sheet_name, rows in sheets.items():
                if first:
                    ws = wb.create_sheet(sheet_name, 0)
                    first = False
                else:
                    ws = wb.create_sheet(sheet_name)
                for row_data in rows:
                    ws.append(row_data)

            file_path.parent.mkdir(parents=True, exist_ok=True)
            wb.save(str(file_path))
            return f"Created: {file_path} ({len(sheets)} sheet(s))"
        except Exception as e:
            return f"Error writing {file_path.name}: {e}"
