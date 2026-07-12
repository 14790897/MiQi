"""Verify MOF skill output matches expected schema and content."""
import json
import os
import sys
import glob as _glob
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

workspace = sys.argv[1]
expected_prefix = sys.argv[2] if len(sys.argv) > 2 else None

result = {"pass": True, "checks": []}

def check(label, condition, detail=""):
    result["checks"].append({"label": label, "pass": bool(condition), "detail": detail})
    if not condition:
        result["pass"] = False

# Find agent extraction JSON
json_files = _glob.glob(os.path.join(workspace, "**", "*_agent_extraction.json"), recursive=True)
if expected_prefix:
    json_files = [f for f in json_files if expected_prefix in os.path.basename(f)]

if not json_files:
    check("find agent_extraction.json", False,
          f"no *_agent_extraction.json found in workspace (prefix={expected_prefix})")
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.exit(1)

filepath = max(json_files, key=os.path.getmtime)
check("find agent_extraction.json", True, f"found: {filepath}")

# Parse JSON
try:
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)
except (json.JSONDecodeError, OSError) as e:
    check("valid JSON", False, str(e))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.exit(1)

check("valid JSON", True)

# ── synthesis_routes ──
routes = data.get("synthesis_routes", [])
check("synthesis_routes is array", isinstance(routes, list), f"type={type(routes).__name__}")
check("route count >= 2", len(routes) >= 2, f"got {len(routes)}")

expected_compounds = ["NH2-UiO-66", "UiO-66"]
for cpd in expected_compounds:
    found = any(cpd.lower() in r.get("target_compound", "").lower() for r in routes)
    check(f"route contains {cpd}", found)

for r in routes:
    cpd = r.get("target_compound", "?")
    check(f"route {cpd}: has procedure_text",
          bool(r.get("procedure_text")), f"len={len(r.get('procedure_text',''))}")
    check(f"route {cpd}: has source",
          r.get("source") in {"main_text", "si", "reference"}, f"got {r.get('source')}")

# ── reagents ──
reagents = data.get("reagents", [])
check("reagents is array", isinstance(reagents, list), f"type={type(reagents).__name__}")
check("reagent count >= 4", len(reagents) >= 4, f"got {len(reagents)}")

expected_reagents = {"ZrCl4": None, "NH2-BDC": None, "H2-BDC": None, "DMF": None}
for r in reagents:
    name = r.get("name", "")
    name_lower = name.lower()
    for exp in expected_reagents:
        if expected_reagents[exp] is not None:
            continue  # already matched
        exp_lower = exp.lower()
        # exact match first, then exact-token match, then substring
        if name_lower == exp_lower:
            expected_reagents[exp] = name
            break
for r in reagents:
    name = r.get("name", "")
    name_lower = name.lower()
    for exp in expected_reagents:
        if expected_reagents[exp] is not None:
            continue
        exp_lower = exp.lower()
        if exp_lower in name_lower:
            expected_reagents[exp] = name

for exp_name, found_name in expected_reagents.items():
    check(f"reagent found: {exp_name}", found_name is not None,
          f"matched={found_name}" if found_name else "not found")

for r in reagents:
    name = r.get("name", "?")
    check(f"reagent {name}: has CAS", bool(r.get("cas")),
          f"got {r.get('cas')}")
    check(f"reagent {name}: has role",
          r.get("role") in {"reactant", "ligand", "solvent", "catalyst", "workup", "modulator"},
          f"got {r.get('role')}")

# ── synthesis_summary ──
summary = data.get("synthesis_summary", "")
if isinstance(summary, dict):
    check("synthesis_summary not empty", bool(summary),
          f"keys={list(summary.keys())}")
elif isinstance(summary, str):
    check("synthesis_summary not empty", bool(summary and summary.strip()),
          f"len={len(summary)}")
else:
    check("synthesis_summary not empty", bool(summary),
          f"type={type(summary).__name__}")

# ── Output files check ──
prefix = Path(filepath).stem.replace("_agent_extraction", "")
base_dir = Path(filepath).parent
expected_files = {
    "routes_csv": f"{prefix}_routes.csv",
    "reagents_csv": f"{prefix}_reagents.csv",
    "synthesis_summary_md": f"{prefix}_synthesis_summary.md",
}
for key, fname in expected_files.items():
    exists = (base_dir / fname).exists()
    check(f"output {key}: {fname}", exists,
          "exists" if exists else "missing")

json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
sys.exit(0 if result["pass"] else 1)
