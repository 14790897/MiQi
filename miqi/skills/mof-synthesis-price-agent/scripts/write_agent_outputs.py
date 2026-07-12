#!/usr/bin/env python
"""Write Codex-agent MOF extraction JSON to the project CSV contract.

Input JSON shape:
{
  "synthesis_routes": [...],
  "reagents": [...],
  "synthesis_summary": "...",      # optional
  "feasibility": {...}              # optional
}
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ROLES = {"reactant", "solvent", "catalyst", "ligand", "modulator", "workup"}
SOURCES = {"main_text", "SI"}


def _norm(value: Any) -> str:
    return re.sub(r"[\s,;，；()（）\[\]]+", "", str(value or "").lower())


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON must be an object.")
    return data


def _as_float_or_none(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric or null, got {value!r}") from exc


def _as_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    raise ValueError(f"{field} must be boolean-like, got {value!r}")


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer, got {value!r}") from exc


def validate(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    routes = data.get("synthesis_routes", [])
    reagents = data.get("reagents", [])
    if not isinstance(routes, list):
        raise ValueError("synthesis_routes must be a list.")
    if not isinstance(reagents, list):
        raise ValueError("reagents must be a list.")
    if not routes:
        raise ValueError("synthesis_routes is empty.")

    clean_routes: list[dict[str, Any]] = []
    for idx, route in enumerate(routes):
        if not isinstance(route, dict):
            raise ValueError(f"synthesis_routes[{idx}] must be an object.")
        target = str(route.get("target_compound") or "").strip()
        procedure = str(route.get("procedure_text") or "").strip()
        source = route.get("source") or "main_text"
        if not target:
            raise ValueError(f"synthesis_routes[{idx}].target_compound is required.")
        if not procedure:
            raise ValueError(f"synthesis_routes[{idx}].procedure_text is required.")
        if source not in SOURCES:
            raise ValueError(f"synthesis_routes[{idx}].source must be main_text or SI.")
        clean_routes.append({
            "target_compound": target,
            "yield_percent": _as_float_or_none(route.get("yield_percent"), f"synthesis_routes[{idx}].yield_percent"),
            "temperature": route.get("temperature"),
            "duration": route.get("duration"),
            "atmosphere": route.get("atmosphere"),
            "procedure_text": procedure,
            "source": source,
            "route_type": route.get("route_type") or "primary",
            "source_text": route.get("source_text"),
        })

    targets_by_route = {i: _norm(r["target_compound"]) for i, r in enumerate(clean_routes)}
    clean_reagents: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for idx, reagent in enumerate(reagents):
        if not isinstance(reagent, dict):
            raise ValueError(f"reagents[{idx}] must be an object.")
        name = str(reagent.get("name") or "").strip()
        role = reagent.get("role")
        route_index = _as_int(reagent.get("route_index", 0), f"reagents[{idx}].route_index")
        if not name:
            raise ValueError(f"reagents[{idx}].name is required.")
        if role not in ROLES:
            raise ValueError(f"reagents[{idx}].role must be one of {sorted(ROLES)}, got {role!r}.")
        if route_index != -1 and route_index not in targets_by_route:
            raise ValueError(f"reagents[{idx}].route_index {route_index} is not valid for {len(clean_routes)} route(s).")
        if route_index != -1 and _norm(name) == targets_by_route[route_index]:
            raise ValueError(f"reagents[{idx}] appears to be the final product for its own route: {name!r}.")
        key = (_norm(name), route_index, str(role))
        if key in seen:
            continue
        seen.add(key)
        clean_reagents.append({
            "name": name,
            "name_zh": reagent.get("name_zh"),
            "name_en": reagent.get("name_en"),
            "cas": reagent.get("cas"),
            "role": role,
            "amount": reagent.get("amount"),
            "equiv": reagent.get("equiv"),
            "route_index": route_index,
            "is_controlled": _as_bool(reagent.get("is_controlled", False), f"reagents[{idx}].is_controlled"),
            "pricing": reagent.get("pricing") or [],
            "fire_hazard": reagent.get("fire_hazard"),
            "fire_hazard_basis": reagent.get("fire_hazard_basis"),
            "ghs_hazards": reagent.get("ghs_hazards"),
            "scraped_at": reagent.get("scraped_at"),
        })

    if not clean_reagents:
        raise ValueError("reagents is empty.")
    return clean_routes, clean_reagents


def write_routes(routes: list[dict[str, Any]], prefix: Path) -> Path:
    path = prefix.parent / f"{prefix.name}_routes.csv"
    fields = [
        "route_index", "target_compound", "yield_percent", "temperature",
        "duration", "atmosphere", "procedure_text", "source", "route_type", "source_text",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for idx, route in enumerate(routes):
            writer.writerow({
                "route_index": idx,
                "target_compound": route["target_compound"],
                "yield_percent": route.get("yield_percent"),
                "temperature": route.get("temperature") or "",
                "duration": route.get("duration") or "",
                "atmosphere": route.get("atmosphere") or "",
                "procedure_text": route["procedure_text"],
                "source": route["source"],
                "route_type": route.get("route_type") or "primary",
                "source_text": route.get("source_text") or "",
            })
    return path


def write_reagents(reagents: list[dict[str, Any]], routes: list[dict[str, Any]], prefix: Path) -> Path:
    path = prefix.parent / f"{prefix.name}_reagents.csv"
    route_map = {idx: route["target_compound"] for idx, route in enumerate(routes)}
    fields = ["name", "cas", "role", "amount", "equiv", "is_controlled", "route_index", "target_compound"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for reagent in reagents:
            route_index = reagent["route_index"]
            writer.writerow({
                "name": reagent["name"],
                "cas": reagent.get("cas") or "",
                "role": reagent["role"],
                "amount": reagent.get("amount") or "",
                "equiv": reagent.get("equiv") if reagent.get("equiv") is not None else "",
                "is_controlled": reagent["is_controlled"],
                "route_index": route_index,
                "target_compound": "universal" if route_index == -1 else route_map.get(route_index, ""),
            })
    return path


def write_optional_artifacts(data: dict[str, Any], prefix: Path, routes: list[dict[str, Any]], reagents: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    summary = data.get("synthesis_summary")
    if isinstance(summary, str) and summary.strip():
        path = prefix.parent / f"{prefix.name}_synthesis_summary.md"
        path.write_text(summary, encoding="utf-8")
        paths.append(path)
    feasibility = data.get("feasibility")
    if isinstance(feasibility, dict) and feasibility:
        path = prefix.parent / f"{prefix.name}_feasibility.json"
        path.write_text(json.dumps(feasibility, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(path)
    extraction_path = prefix.parent / f"{prefix.name}_agent_extraction.json"
    extraction_path.write_text(
        json.dumps({
            "synthesis_routes": routes,
            "reagents": reagents,
            "synthesis_summary": summary or "",
            "feasibility": feasibility,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths.append(extraction_path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Write agent MOF extraction JSON to standard pipeline CSV files.")
    parser.add_argument("input_json", type=Path, help="Agent extraction JSON file.")
    parser.add_argument("output_prefix", type=Path, help="Output prefix, e.g. output/paper_cleaned.")
    parser.add_argument("--write-json-copy", action="store_true", help="Deprecated; validated JSON is always saved beside the CSV files.")
    parser.add_argument("--status-json", type=Path, help="Optional path for a compact machine-readable status JSON.")
    args = parser.parse_args()

    try:
        data = _load_json(args.input_json)
        routes, reagents = validate(data)
        args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
        routes_path = write_routes(routes, args.output_prefix)
        reagents_path = write_reagents(reagents, routes, args.output_prefix)
        optional_paths = write_optional_artifacts(data, args.output_prefix, routes, reagents)
        created = [str(p) for p in optional_paths] + [str(routes_path), str(reagents_path)]
        if args.status_json:
            args.status_json.parent.mkdir(parents=True, exist_ok=True)
            args.status_json.write_text(
                json.dumps({
                    "completion_state": "complete",
                    "prefix": str(args.output_prefix),
                    "created_files": created,
                    "counts": {"routes": len(routes), "reagents": len(reagents)},
                    "next_action": "Run enrichment/report workflow for this prefix.",
                    "missing_or_failed": [],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        for artifact in optional_paths:
            print(artifact)
        print(routes_path)
        print(reagents_path)
        return 0
    except Exception as exc:
        if "args" in locals() and getattr(args, "status_json", None):
            args.status_json.parent.mkdir(parents=True, exist_ok=True)
            args.status_json.write_text(
                json.dumps({
                    "completion_state": "evidence_boundary",
                    "prefix": str(getattr(args, "output_prefix", "")),
                    "created_files": [],
                    "counts": {},
                    "next_action": "Repair the agent JSON once using the validation error and source evidence.",
                    "missing_or_failed": [str(exc)],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
