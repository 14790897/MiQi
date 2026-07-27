"""Batch-migrate remaining hand-rolled modals to shared Modal component."""
import re, os

BASE = r"D:\Desktop\jiagou\MiQi\apps\desktop\src\renderer"

MIGRATIONS = [
    # SkillsPage — CreateSkillModal
    {
        "file": f"{BASE}/features/skills/SkillsPage.tsx",
        "modal_import": 'import { Modal } from \'../../components/shared\';\n',
        # Replace wrapper opening
        "find_open": '    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">',
        "replace_open": '    <Modal open={!!open} onOpenChange={(o) => { if (!o) onClose(); }} hideClose>',
        # Replace wrapper closing (rough — find the last two </div> before )
        "find_close_pattern": "inner_div_close + outer_div_close",
    },
]

# Actually this is too complex for regex. Let me use a simpler approach:
# Just run sed to add Modal imports to files that need them,
# Then manually verify with tsc

print("Starting batch migration...")
print("Files to process:", len(MIGRATIONS))
print("Done — using manual approach instead.")
