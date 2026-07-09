"""Verify latest pptx-generator output in workspace matches prompt spec."""
import json, os, sys, glob
from pathlib import Path
from pptx import Presentation

workspace = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(r"~\.miqi\workspace")
files = glob.glob(os.path.join(workspace, "*.pptx"))
if not files:
    json.dump({"pass": False, "checks": [{"label": "find pptx", "pass": False, "detail": "no pptx found"}]}, sys.stdout)
    sys.exit(1)

filepath = max(files, key=os.path.getmtime)
prs = Presentation(filepath)

texts = []
for s in prs.slides:
    for sh in s.shapes:
        if sh.has_text_frame:
            for p in sh.text_frame.paragraphs:
                t = p.text.strip()
                if t:
                    texts.append(t)

all_text = "\n".join(texts)
result = {
    "slides": len(prs.slides),
    "texts": texts,
    "pass": True,
    "checks": [],
}

def check(label, condition, detail=""):
    result["checks"].append({"label": label, "pass": bool(condition), "detail": detail})
    if not condition:
        result["pass"] = False

check("slide count >= 1", len(prs.slides) >= 1, f"got {len(prs.slides)}")
check("cover title", "人工智能简介" in texts[0] if texts else False)

json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
sys.exit(0 if result["pass"] else 1)
