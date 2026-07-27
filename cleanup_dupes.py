#!/usr/bin/env python3
"""Remove duplicate local function definitions from ChatConsole.tsx."""
import re

path = r"D:\Desktop\jiagou\MiQi\apps\desktop\src\renderer\features\chat\ChatConsole.tsx"

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Functions to remove (start line numbers, 1-indexed)
to_remove = {
    'AgentAvatar': 3596,
    'UserAvatar': 3607,
    'stripThinkBlocks': 3621,
    'MarkdownContent': 3627,
    'DiffView': 3095,
    'TrackedFileCard': 3163,
}

# Find end of each function by tracking brace depth
def find_function_end(lines, start_idx):
    """Find the line index (0-indexed) where the function at start_idx ends."""
    depth = 0
    started = False
    for i in range(start_idx, len(lines)):
        line = lines[i]
        # Count braces
        for ch in line:
            if ch == '{':
                depth += 1
                started = True
            elif ch == '}':
                depth -= 1
        if started and depth == 0:
            return i  # inclusive — this line has the closing }
    return len(lines) - 1

# Sort by start line descending to remove from bottom up
removals = []
for name, start_line in sorted(to_remove.items(), key=lambda x: -x[1]):
    start_idx = start_line - 1  # 0-indexed
    end_idx = find_function_end(lines, start_idx)
    
    # Include the blank line before the function if present
    if start_idx > 0 and lines[start_idx - 1].strip() == '':
        start_idx -= 1
    
    print(f"Removing {name}: lines {start_idx+1}-{end_idx+1} ({end_idx - start_idx + 1} lines)")
    removals.append((start_idx, end_idx))

# Build new lines
to_skip = set()
for s, e in removals:
    for i in range(s, e + 1):
        to_skip.add(i)

new_lines = [lines[i] for i in range(len(lines)) if i not in to_skip]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"\nRemoved {len(to_skip)} lines total.")
print(f"Before: {len(lines)} lines, After: {len(new_lines)} lines")
