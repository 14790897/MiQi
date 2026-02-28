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

## Feishu File Upload — Mandatory Permission Workflow

**Every time you upload a file or create a document via feishu-mcp, you MUST
grant full permissions to the current chat group immediately after the upload.**
Never skip this step — files uploaded without explicit permissions will show
"Access Denied" to group members.

### For uploaded files (`upload_file` or `upload_file_and_share`)

After obtaining `file_token`, call these two tools in order:

```
# Step 1: make the file accessible via link (anyone in the org)
mcp_feishu-mcp_set_doc_public_access(
    file_token = <file_token>,
    file_type  = "file",
    access_level = "tenant_readable"
)

# Step 2: grant the CURRENT GROUP full_access (can view, download, and manage)
mcp_feishu-mcp_set_doc_permission(
    file_token       = <file_token>,
    file_type        = "file",
    chat_ids         = [<current_chat_id>],   # the oc_xxx group this message came from
    perm_type        = "full_access"
)
```

Then send the share link to the group:

```
mcp_feishu-mcp_get_share_link(file_token=<file_token>, file_type="file")
# → send the returned URL via send_message / reply_message
```

`upload_file_and_share` already handles Step 1 internally; you still MUST call
Step 2 (`set_doc_permission`) afterwards to grant the group `full_access`.

### For created documents (`create_document`)

After creating and writing a document, use `docx` as the `file_type`:

```
mcp_feishu-mcp_set_doc_public_access(
    file_token   = <document_id>,
    file_type    = "docx",
    access_level = "tenant_readable"
)

mcp_feishu-mcp_set_doc_permission(
    file_token       = <document_id>,
    file_type        = "docx",
    chat_ids         = [<current_chat_id>],
    perm_type        = "full_access"
)
```

### Multiple files (e.g. pdf2zh mono + dual output)

When uploading multiple files at once, run both permission steps for **each**
`file_token` individually. Do not share a single token's permissions with
another file.

### Permission level reference

| `perm_type` value | Meaning |
|---|---|
| `view` | Read-only |
| `edit` | Can edit content |
| `full_access` | Full control (view, edit, share, manage) — use this |

### `set_doc_permission` error 1063003

If `set_doc_permission` returns error `1063003`, the bot is not in the target
group. Inform the user: "请将飞书机器人添加到群组：群设置 → 群机器人 → 添加机器人"。
Do NOT silently skip permissions — at minimum ensure `set_doc_public_access` is
called so the link is still accessible.
