#!/usr/bin/env python3
"""Extract MessageBubble from ChatConsole.tsx to its own file."""

chat_path = r"D:\Desktop\jiagou\MiQi\apps\desktop\src\renderer\features\chat\ChatConsole.tsx"
comp_path = r"D:\Desktop\jiagou\MiQi\apps\desktop\src\renderer\features\chat\components\MessageBubble.tsx"

with open(chat_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# MessageBubble is lines 3108-3430 (1-indexed), or 3107-3429 (0-indexed)
start_idx = 3107  # 0-indexed
end_idx = 3429    # 0-indexed, inclusive

# Extract the function body
msg_bubble_lines = lines[start_idx:end_idx + 1]

# Write to new file
header = """import { useState } from 'react';
import { cn } from '../../../lib/utils';
import { AgentAvatar } from './Avatars';
import { MarkdownContent } from './MarkdownContent';
import PaperSearchResult from '../PaperSearchResult';
import type { Message, PaperItem } from '../../../../shared/ipc';

"""
with open(comp_path, 'w', encoding='utf-8') as f:
    f.write(header)
    f.writelines(msg_bubble_lines)

print(f"Wrote {len(msg_bubble_lines)} lines to {comp_path}")

# Remove from ChatConsole (keep the empty line + comment before it)
# Remove lines 3107-3429
new_lines = lines[:start_idx] + lines[end_idx + 1:]

# Add import
import_line = "import { MessageBubble } from './components/MessageBubble';\n"
# Insert after the other component imports
for i, line in enumerate(new_lines):
    if "import { TrackedFileCard } from './components/TrackedFileCard';" in line:
        new_lines.insert(i + 1, import_line)
        break

with open(chat_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

removed = end_idx - start_idx + 1
print(f"Removed {removed} lines from ChatConsole.tsx")
print(f"ChatConsole: {len(lines)} → {len(new_lines)} lines")
