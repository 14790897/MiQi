#!/usr/bin/env python3
"""Safely replace inline style={{var(--xxx)}} with Tailwind classes by merging into existing className."""
import re, os, sys

BASE = r"D:\Desktop\jiagou\MiQi\apps\desktop\src\renderer"

# Mapping: var(--xxx) patterns → Tailwind class to append
STYLE_TO_CLASS = {
    "color: 'var(--text)'": "text-text",
    'color: "var(--text)"': "text-text",
    "color: 'var(--text-muted)'": "text-text-muted",
    'color: "var(--text-muted)"': "text-text-muted",
    "color: 'var(--text-faint)'": "text-text-faint",
    'color: "var(--text-faint)"': "text-text-faint",
    "background: 'var(--surface)'": "bg-surface",
    'background: "var(--surface)"': "bg-surface",
    "background: 'var(--surface-muted)'": "bg-surface-muted",
    'background: "var(--surface-muted)"': "bg-surface-muted",
    "borderColor: 'var(--border)'": "border-border",
    'borderColor: "var(--border)"': "border-border",
    "borderColor: 'var(--border-subtle)'": "border-border-subtle",
    'borderColor: "var(--border-subtle)"': "border-border-subtle",
}

# For each file, find patterns like:
#   className="some classes" style={{ color: 'var(--text-muted)' }}
# or:
#   className={"some classes"}
#   style={{ color: 'var(--text-muted)' }}
# 
# Strategy: find each style={{...}} on a single line, look backwards for className on the same or previous line

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    changed = False
    
    for style_pattern, tailwind_class in STYLE_TO_CLASS.items():
        # Pattern: style={{ <pattern> }}
        full_style = f"style={{{{ {style_pattern} }}}}"
        if full_style not in content:
            continue
        
        # Find each occurrence and try to merge with className
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            if full_style in line:
                # Look backward for className on same line or previous 1-2 lines
                # Pattern 1: className="..." on same line
                cm = re.search(r'className="([^"]*)"', line)
                if cm:
                    existing = cm.group(1)
                    if tailwind_class not in existing.split():
                        new_cn = f'{existing} {tailwind_class}'.strip()
                        line = line[:cm.start(1)] + new_cn + line[cm.end(1):]
                        changed = True
                    # Remove style part — match with optional leading space to prevent double-spaces
                    line = line.replace(' ' + full_style, '')
                    line = line.replace(full_style, '')  # fallback if no leading space
                    lines[i] = line
                else:
                    # Pattern 2: className on previous line
                    if i > 0 and 'className="' in lines[i-1]:
                        prev = lines[i-1]
                        cm2 = re.search(r'className="([^"]*)"', prev)
                        if cm2:
                            existing = cm2.group(1)
                            if tailwind_class not in existing.split():
                                new_cn = f'{existing} {tailwind_class}'.strip()
                                lines[i-1] = prev[:cm2.start(1)] + new_cn + prev[cm2.end(1):]
                                changed = True
                        lines[i] = lines[i].replace(' ' + full_style, '')
                        lines[i] = lines[i].replace(full_style, '')
                        if not lines[i].strip():
                            lines.pop(i)
                            i -= 1
                    # Pattern 3: No className found — skip this occurrence
            i += 1
        content = '\n'.join(lines)
    
    if changed and content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

# Walk all .tsx files
count = 0
for root, dirs, files in os.walk(BASE):
    for f in files:
        if f.endswith('.tsx'):
            fp = os.path.join(root, f)
            if process_file(fp):
                count += 1
                print(f"  ✓ {os.path.relpath(fp, BASE)}")

print(f"\nModified {count} files")
