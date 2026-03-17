---
name: memory
description: RAM-first memory system with automatic short-term and long-term recall.
always: true
---

# Memory

## Structure

- `memory/MEMORY.md` — Long-term facts (preferences, project context, relationships). Always loaded into your context.
- `memory/LTM_SNAPSHOT.json` — Auto-maintained long-term memory snapshot.
- `memory/LESSONS.jsonl` — Self-improvement lessons learned from interactions.

## When to Update MEMORY.md

Write important facts immediately using `edit_file` or `write_file`:
- User preferences ("I prefer dark mode")
- Project context ("The API uses OAuth2")
- Relationships ("Alice is the project lead")

## Auto-consolidation

Old conversations are automatically summarized into RAM-based short-term memory when the session grows large. Long-term facts are extracted to MEMORY.md and LTM_SNAPSHOT.json. You don't need to manage this.
