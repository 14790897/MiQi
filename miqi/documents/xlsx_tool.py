"""Excel (.xlsx) read/write tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from miqi.agent.tools.base import Tool


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
    # write tools default to workspace as the boundary.
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
        file_path = Path(kwargs.get("file_path") or kwargs.get("path", ""))
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

        raw_path = kwargs.get("file_path") or kwargs.get("path", "")
        sheets = kwargs["sheets"]

        try:
            file_path = _resolve_output_path(
                raw_path, self._workspace, self._allowed_dir,
            )
        except PermissionError as e:
            return f"Error: Permission denied: {e}"

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
            return f"Error writing {raw_path}: {e}"
