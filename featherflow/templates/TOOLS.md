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

## paper_download

- Use this tool to download paper PDFs into workspace.
- It detects common paywall/login interstitial pages and returns structured errors instead of saving fake PDFs.

## Feishu File Messages — Required Workflow

When a message starts with `[收到文件]`, `[收到图片]`, `[收到语音]`, or `[收到视频]`,
the user has uploaded a file attachment in the chat. **Always follow this workflow:**

1. **Download first** — call `mcp_feishu-mcp_download_message_file` with the
   `message_id` and `file_key` shown in the message. Do NOT guess or assume the
   file already exists at any local path.
2. **Use the returned local path** — the tool returns the saved file path on disk.
   Use that exact path for all subsequent processing (translation, analysis, etc.).
3. **Never skip the download step** — the file does not exist locally until you
   download it. Any tool call using a guessed path will fail.
