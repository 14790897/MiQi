#!/usr/bin/env python
"""Normalize DOI/link tables to a UTF-8-SIG CSV with columns doi,link."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

DOI_RE = re.compile(r"10\.\d{4,}/[^\s,;\"']+", re.I)


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _extract_doi(value: Any) -> str:
    match = DOI_RE.search(_clean_cell(value))
    if not match:
        return ""
    doi = match.group(0)
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    return doi.rstrip(".。),，;；]】}>")


def _looks_like_link(value: Any) -> str:
    text = _clean_cell(value)
    if text.startswith(("http://", "https://")):
        return text
    return ""


def _read_rows(path: Path, sheet: str | int | None) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with path.open("r", encoding=encoding, newline="") as f:
                    return list(csv.DictReader(f, delimiter=delimiter))
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError("unknown", b"", 0, 1, "Unable to decode CSV/TSV as utf-8-sig, utf-8, or gbk.")
    if suffix in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("pandas/openpyxl is required for Excel input.") from exc
        df = pd.read_excel(path, sheet_name=sheet if sheet is not None else 0)
        return df.to_dict("records")
    raise ValueError("Input must be .csv, .tsv, .xlsx, or .xls.")


def normalize(path: Path, output: Path, doi_column: str | None, link_column: str | None, sheet: str | int | None) -> int:
    rows = _read_rows(path, sheet)
    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        keys = list(row.keys())
        doi = ""
        if doi_column and doi_column in row:
            doi = _extract_doi(row.get(doi_column))
        if not doi:
            for key in keys:
                if str(key).strip().lower() == "doi":
                    doi = _extract_doi(row.get(key))
                    break
        if not doi:
            for key in keys[:10]:
                doi = _extract_doi(row.get(key))
                if doi:
                    break
        if not doi or doi in seen:
            continue

        link = ""
        if link_column and link_column in row:
            link = _looks_like_link(row.get(link_column))
        if not link:
            for key in keys:
                if str(key).strip().lower() == "link":
                    link = _looks_like_link(row.get(key))
                    break
        if not link:
            for key in keys:
                link = _looks_like_link(row.get(key))
                if link:
                    break
        seen.add(doi)
        pairs.append((doi, link))

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["doi", "link"])
        writer.writerows(pairs)
    return len(pairs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a doi,link CSV for the MOF paper pipeline.")
    parser.add_argument("input", type=Path, help="Source CSV/TSV/XLSX/XLS file.")
    parser.add_argument("-o", "--output", type=Path, default=Path("dois.csv"), help="Output CSV path.")
    parser.add_argument("--doi-column", help="Explicit DOI column name.")
    parser.add_argument("--link-column", help="Explicit link column name.")
    parser.add_argument("--sheet", help="Excel sheet name or zero-based index.")
    args = parser.parse_args()

    sheet: str | int | None = args.sheet
    if isinstance(sheet, str) and sheet.isdigit():
        sheet = int(sheet)

    try:
        count = normalize(args.input, args.output, args.doi_column, args.link_column, sheet)
        if count:
            print(f"Wrote {count} DOI row(s) to {args.output}")
            return 0
        print("未找到有效 DOI。请确认表格中至少有一列包含 10.xxxx/... 格式 DOI。", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"DOI/link 表格规范化失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
