---
name: cron
description: Schedule reminders and recurring tasks.
---

# Cron

Use the `cron` tool to schedule reminders or recurring tasks.

## Three Modes

1. **Reminder** - message is sent directly to user
2. **Task** - message is a task description, agent executes and sends result
3. **One-time** - runs once at a specific time, then auto-deletes

## Examples

Fixed reminder:
```
cron(action="add", message="Time to take a break!", every_seconds=1200)
```

Dynamic task (agent executes each time):
```
cron(action="add", message="Check my repository GitHub stars and report", every_seconds=600)
```

One-time scheduled task — **always include a timezone offset or pass `tz`**:
```
cron(action="add", message="Remind me about the meeting", at="2026-03-20T09:00:00+08:00")
# or: at="2026-03-20T09:00:00", tz="Asia/Shanghai"
```

Timezone-aware cron:
```
cron(action="add", message="Morning standup", cron_expr="0 9 * * 1-5", tz="Asia/Shanghai")
cron(action="add", message="Morning standup", cron_expr="0 9 * * 1-5", tz="America/Vancouver")
```

List/remove:
```
cron(action="list")
cron(action="remove", job_id="abc123")
```

## Time Expressions

| User says | Parameters |
|-----------|------------|
| every 20 minutes | every_seconds: 1200 |
| every hour | every_seconds: 3600 |
| every day at 8am (China) | cron_expr: "0 8 * * *", tz: "Asia/Shanghai" |
| weekdays at 5pm (China) | cron_expr: "0 17 * * 1-5", tz: "Asia/Shanghai" |
| 9am Vancouver time daily | cron_expr: "0 9 * * *", tz: "America/Vancouver" |
| at a specific time | at: ISO datetime **with timezone offset** (e.g. "2026-03-20T09:00:00+08:00") |

## Timezone

- **`cron_expr` without `tz`**: evaluated in **UTC**. Always pass `tz` when user's intent is in a non-UTC timezone.
- **`at` without timezone offset**: naive datetime is interpreted as **UTC**. Use `+08:00` suffix or pass `tz="Asia/Shanghai"` for China Standard Time.
- `tz` accepts IANA timezone names: `Asia/Shanghai`, `America/Vancouver`, `Europe/London`, etc.
