# Self-Improvement

MiQi includes a lightweight **feedback-to-lessons** loop that allows the agent to learn from mistakes and user corrections without requiring embeddings or external retrieval systems.

---

## Overview

```
Detect mistake / correction
        ↓
Convert to structured lesson
        ↓
Inject relevant lessons in future prompts
        ↓
Reinforce or compact over time
```

---

## Lesson Schema

Each lesson is stored as a JSON object in `~/.miqi/memory/LESSONS.jsonl`:

```json
{
  "id": "lesson_abc123",
  "trigger": "tool:read_file:error",
  "bad_action": "Called read_file without checking path existence",
  "better_action": "Check path existence before calling read_file",
  "scope": "global",
  "confidence": 0.85,
  "hits": 3,
  "source": "tool_feedback",
  "created_at": "2026-02-13T09:01:10.223000"
}
```

---

## Learning Sources

### Tool Feedback

When a tool returns an error result, MiQi learns a tool-specific lesson. Examples:

| Trigger | Better Action |
|---|---|
| `tool:read_file:error` | Check path existence before calling `read_file` |
| `tool:exec:error` | Validate command syntax before running `exec` |
| `tool:web_fetch:error` | Verify URL is reachable before calling `web_fetch` |

### User Feedback

When users provide correction-style feedback, MiQi learns a response lesson. To reduce false positives:

- Previous assistant output must exist in the session
- Message length must be within `feedbackMaxMessageChars`
- By default, correction cue must appear **as a prefix** (`feedbackRequirePrefix=true`)

Example learned lesson:

```json
{
  "trigger": "response:length",
  "better_action": "Keep responses shorter unless detailed output is requested"
}
```

---

## Prompt Injection

At context build time, MiQi selects the top lessons by:

1. **Scope match** — `session` lessons apply to the current session; `global` lessons apply everywhere
2. **Confidence threshold** — lessons below `minLessonConfidence` are excluded
3. **Time decay** — confidence decays after `lessonConfidenceDecayHours` since last use
4. **Lexical relevance** — normalized keyword overlap with the current message
5. **Recency/hits tie-break** — more frequently reinforced lessons rank higher

Selected lessons are injected into the `## Lessons` section of the memory context.

---

## Session-to-Global Promotion

Repeated session lessons can be automatically promoted to global scope when:

- Lesson source is user feedback
- Trigger matches `promotionTriggers`
- Distinct user count reaches `promotionMinUsers`

Promotion is conservative: the session lesson is kept, and a new global lesson is added.

---

## Configuration

All settings are under `agents.selfImprovement` in `~/.miqi/config.json`:

| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable/disable the self-improvement system |
| `maxLessonsInPrompt` | `5` | Maximum lessons injected per prompt |
| `minLessonConfidence` | `0.5` | Minimum confidence to include a lesson |
| `maxLessons` | `500` | Maximum lessons retained in the store |
| `lessonConfidenceDecayHours` | `168` | Hours before confidence decay begins |
| `feedbackMaxMessageChars` | `500` | Max message length to treat as user feedback |
| `feedbackRequirePrefix` | `true` | Require correction cue as a message prefix |
| `promotionEnabled` | `true` | Allow session-to-global promotion |
| `promotionMinUsers` | `2` | Min distinct users to trigger promotion |
| `promotionTriggers` | `[]` | Trigger pattern list for promotion candidates |

---

## Management Commands {#management-commands}

```bash
# Inspect lessons
miqi memory lessons status
miqi memory lessons list [--scope global|session] [--limit N]

# Control lesson behavior
miqi memory lessons enable <id>
miqi memory lessons disable <id>
miqi memory lessons delete <id>

# Bulk operations
miqi memory lessons compact [--max-lessons N]
miqi memory lessons reset
```
