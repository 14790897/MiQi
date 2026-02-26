# Tool Usage Notes

Tool signatures are provided automatically via function calling.
This file documents non-obvious constraints and usage patterns.

## exec — Safety Limits

- Commands have a configurable timeout (default 60s)
- Dangerous commands are blocked (rm -rf, format, dd, shutdown, etc.)
- Output is truncated at 10,000 characters
- `restrictToWorkspace` config can limit file access to the workspace

## cron — Scheduled Reminders

- Please refer to cron skill for usage.

## feishu_doc / feishu_calendar / feishu_task

- These tools only work when current channel is `feishu`.
- For group assignment, pass assignees/attendees as `open_id` or exact display names.
- In group chats, user resolution first uses message mentions, then falls back to group member list.
- If names are ambiguous, the tool returns candidates instead of guessing.

## paper_download

- Use this tool to download paper PDFs into workspace.
- It detects common paywall/login interstitial pages and returns structured errors instead of saving fake PDFs.

## feishu_drive

- Use `ensure_folder_path` before uploads to keep research artifacts organized in Drive.
- Upload paths must stay inside workspace; external absolute paths are blocked.

## feishu_handoff

- This is the generic collaboration handoff layer, not a scenario-specific tool.
- It orchestrates archive/upload + optional summary doc + optional task/calendar in one call.
- Keep this as the default "delivery" path; use lower-level tools for exception handling/debug.
