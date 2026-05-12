---
name: find-install-skills
description: Search and install skills from the my-skills registry (https://skills.sixiangjia.de). Discover available skills by keyword, then install them into the user's WorkBuddy skills directory.
---

# find-install-skills

Search and install skills from the my-skills registry.

## Registry

- **Index**: `https://skills.sixiangjia.de/index.json`
- **Search API**: `https://skills.sixiangjia.de/api/search?q=<query>`
- **Skill URL pattern**: `https://skills.sixiangjia.de/<skill-name>/SKILL.md`

## When to use

- User asks to find, browse, search, or install a skill from this registry

## Instructions

### Step 1: Search

Use WebFetch to search the registry:

```
curl -s "https://skills.sixiangjia.de/api/search?q=<keyword>"
```

Or browse all available skills:

```
curl -s "https://skills.sixiangjia.de/index.json",
```

### Step 2: Install

1. Write it to the user's skill directory:
   - **User-level**: `~/.workbuddy/skills/<skill-name>/SKILL.md`
   - **Project-level**: `{workspace}/.workbuddy/skills/<skill-name>/SKILL.md`
   - **Nanobot**: `nanobot/skills/<skill-name>/SKILL.md`
   - **miqi**: `miqi/skills/<skill-name>/SKILL.md`

### Step 3: Present results to user

Show the user what's installed in a concise list format:

```
| Skill | Description | URL |
|-------|-------------|-----|
| name  | desc        | url |
```


