---
name: feishu-report
description: "Deliver content to Feishu (飞书) in the appropriate format: plain text for quick replies, card messages for structured info, Feishu Docs for long reports, calendar events for meetings, and tasks for action items. Use whenever the output should go to a Feishu user or group."
metadata: {"featherflow":{"emoji":"💬","requires":{"mcp":["feishu-mcp"]}}}
---

# Feishu Report

Choose the right delivery format. Default to the simplest that fits.

## Format Decision

| Content type | Tool to use |
|-------------|------------|
| Short reply / notification (< 500 chars) | `send_message` or `reply_message` |
| Structured info (table, status, multi-section) | `send_card_message` |
| Long report / research briefing (> 1000 chars) | `create_document` + `write_document_markdown` → `get_share_link` → `send_message` |
| Meeting / event | `create_calendar_event` (+`add_event_attendees`) |
| Action item / to-do | `create_task` (+`assign_task`, `add_task_to_list`) |

---

## 1. Plain Text Message

```python
send_message(
    receive_id_type="chat_id",   # or "open_id" / "email"
    receive_id="<chat_id>",
    content="Your briefing is ready.",
)
```

For @mention someone: use `build_text_with_at` to construct content.

---

## 2. Card Message (Structured)

Use for research briefings, status reports, job results — anything with sections or a table.

```python
send_card_message(
    receive_id_type="chat_id",
    receive_id="<chat_id>",
    card_content='<JSON card>'   # use build_interactive_card() helper or hand-craft
)
```

Basic card structure (Feishu Card JSON):
```json
{
  "config": {"wide_screen_mode": true},
  "elements": [
    {"tag": "div", "text": {"tag": "lark_md", "content": "**Title**\n\nContent here"}},
    {"tag": "hr"},
    {"tag": "div", "text": {"tag": "lark_md", "content": "References:\n[1] ..."}}
  ]
}
```

---

## 3. Feishu Doc (Long Reports)

Best for reports > 1000 characters or content that may be shared / revisited.

```python
# Step 1: create doc (optionally inside a folder)
doc = create_document(title="Quantum Computing Briefing — 2026-03-19")

# Step 2: write Markdown content
write_document_markdown(
    document_id=doc["document_id"],
    markdown="# Quantum Computing Briefing\n\n## Key Findings\n..."
)

# Step 3: get shareable link and notify
link = get_share_link(document_id=doc["document_id"])
send_message(receive_id_type="chat_id", receive_id="<chat_id>",
             content=f"今日量子计算简报已生成：{link['link']}")
```

`write_document_markdown` accepts standard Markdown: headings, bold, italic, lists, code blocks, tables.

---

## 4. Calendar Event

```python
cal = get_or_create_group_calendar()
event = create_calendar_event(
    calendar_id=cal["calendar_id"],
    summary="Team Sync",
    start_time="2026-03-20T10:00:00+08:00",
    end_time="2026-03-20T11:00:00+08:00",
    description="Weekly sync"
)
add_event_attendees(calendar_id=cal["calendar_id"],
                    event_id=event["event_id"],
                    attendee_ids=["<open_id1>", "<open_id2>"])
```

---

## 5. Task

```python
task = create_task(
    title="Review draft report",
    notes="See shared doc: <link>",
    due="2026-03-21T18:00:00+08:00"
)
assign_task(task_id=task["task_id"], member_ids=["<open_id>"])
```

---

## Resolving User Identities

When you only have a name (not open_id), use:
```python
resolve_users_by_name(name="Alice")      # fuzzy match → returns open_id list
get_chat_members(chat_id="<chat_id>")    # list everyone in a group
```
